#!/usr/bin/python
# -a*- coding: utf-8 -*-
#
# Copyright (c) 2011 Benoit HERVIER <khertan@khertan.net>
# Licenced under GPLv3

## This program is free software; you can redistribute it and/or modify
## it under the terms of the GNU General Public License as published
## by the Free Software Foundation; version 3 only.
##
## This program is distributed in the hope that it will be useful,
## but WITHOUT ANY WARRANTY; without even the implied warranty of
## MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.    See the
## GNU General Public License for more details.

import os.path
import os
import threading
from PySide.QtCore import QObject, Slot, Signal, Property
from note import Note, getValidFilename
from settings import Settings
import time
import json
import logger
import logging
import md5util

def basename(path):
    return os.path.basename(path)


class Sync(QObject):
    '''Sync class'''

    def __init__(self,):
        QObject.__init__(self)
        self._running = False
        #logging.getLogger(_defaultLoggerName).setLevel(logging.WARNING)
        self.logger = logger.getDefaultLogger()
        self._localDataFolder = Note.NOTESPATH
        self._remoteDataFolder = 'KhtNotes'

    @Slot()
    def launch(self):
        ''' Sync the notes in a thread'''
        if not self._get_running():
                self._set_running(True)
                self.thread = threading.Thread(target=self._wsync)
                self.thread.start()

    def _wsync(self):
        try:
            self._sync_connect()
        except Exception, err:
            self.on_error.emit(unicode(err))
            self.on_running = False
            self.logger.error('%s:%s' % (unicode(type(err)), unicode(err)))

    def readSettings(self,):
        #Read Settings
        settings = Settings()
        self.webdavHost = settings.webdavHost
        self.webdavBasePath = settings.webdavBasePath
        webdavLogin = settings.webdavLogin
        webdavPasswd = settings.webdavPasswd
        useAutoMerge = settings.autoMerge
        return webdavLogin, webdavPasswd, useAutoMerge

    def createConnection(self, webdavLogin, webdavPasswd):
        from webdav.WebdavClient import CollectionStorer, AuthorizationError, \
                                        parseDigestAuthInfo
        from webdav.logger import _defaultLoggerName

        isConnected = False
        webdavConnection = CollectionStorer(self.webdavHost
                                            + self.webdavBasePath,
                           validateResourceNames=False)
        logging.getLogger(_defaultLoggerName).setLevel(logging.WARNING)

        time_delta = None

        #Test KhtNotes folder and authenticate
        authFailures = 0
        while authFailures < 3:
            try:
                webdavConnection.validate()
                response = webdavConnection.getSpecificOption('date')
                try:
                    import rfc822
                    local_datetime = int(time.time())
                    remote_datetime = rfc822.parsedate(response)
                    time_delta = time.mktime(remote_datetime) - local_datetime
                    self.logger.debug('Time delta: %f' % time_delta)
                except Exception, err:
                    time_delta = None
                    print 'error parsing date', err
                    self.logger.error('Failed to parse datetime: %s:%s'
                                    % (unicode(type(err)), unicode(err)))
                isConnected = True
                break  # break out of the authorization failure counter
            except AuthorizationError, err:
                if err.authType == "Basic":
                    webdavConnection.connection.\
                        addBasicAuthorization(webdavLogin, webdavPasswd)
                elif err.authType == "Digest":
                    info = parseDigestAuthInfo(err.authInfo)
                    webdavConnection.connection.\
                        addDigestAuthorization(webdavLogin,
                                               webdavPasswd,
                                               realm=info["realm"],
                                               qop=info["qop"],
                                               nonce=info["nonce"])
                elif authFailures >= 2:
                    self.on_error.emit('Wrong login or password')
                    self.logger.error('Wrong login or password')
                else:
                    self.logger.error('%s:%s' % (unicode(type(err)),
                                      unicode(err)))
                    self.on_error.emit(unicode(err) + ':' + unicode(err))

            except Exception, err2:
                self.on_error.emit(unicode(type(err2)) + ':' + unicode(err2))
                self.logger.error(unicode(type(err2)) + ':' + unicode(err2))
                print unicode(type(err2)) + ':' + unicode(err2)
            authFailures += 1
        return (isConnected, webdavConnection, time_delta)

    def _sync_connect(self,):
        '''Sync the notes with a webdav server'''
        webdavLogin, webdavPasswd, useAutoMerge = self.readSettings()

        #Create Connection
        isConnected, webdavConnection, time_delta = \
            self.createConnection(webdavLogin, webdavPasswd)
        print 'isConnected: ', isConnected
        if isConnected:
            self._sync_files(webdavConnection, time_delta, useAutoMerge)
        self._set_running(False)
        self.on_finished.emit()


    def _sync_files(self, webdavConnection, time_delta, useAutoMerge):
            try:

                #Reset webdav path
                webdavConnection.path = self.webdavBasePath

                #Check that KhtNotes folder exists at root or create it and
                #and lock Collections
                self._check_khtnotes_folder_and_lock(webdavConnection)

                #Get remote filenames and timestamps
                remote_filenames = \
                    self._get_remote_filenames(webdavConnection)

                #Get local filenames and timestamps
                local_filenames = self._get_local_filenames()

                #Compare with last sync index
                lastsync_remote_filenames, \
                lastsync_local_filenames = self._get_lastsync_filenames()

                #Sync intelligency (or not)
                #It use a local index with timestamp of the server files
                #1/ As most webdav server didn t support setting
                #   modification datetime on ressources
                #2/ Main target is owncloud where webdavserver didn't
                #   implent delta-v versionning
                #3/ Notes should be editable in the owncloud interface
                #   but i would like to support other webdav server
                #   so an owncloud apps isn t acceptable

                #Delete remote file deleted
                for filename in set(lastsync_remote_filenames) \
                                - set(remote_filenames):
                    if filename in local_filenames.keys():
                        if ((lastsync_remote_filenames[filename] -
                          time_delta) + 1) \
                          >= local_filenames[filename]:
                            self._local_delete(filename)
                        else:
                            #Else we have a conflict local file is newer than
                            #deleted one
                            self.logger.debug('Delete conflictServer: %s'
                                              % filename)
                            self._upload(webdavConnection, filename,
                                         None, time_delta)

                #Delete local file deleted
                for filename in set(lastsync_local_filenames) \
                                - set(local_filenames):
                    if filename in remote_filenames:
                        if lastsync_local_filenames[filename] \
                           >= ((remote_filenames[filename] - time_delta) - 1):
                            self._remote_delete(webdavConnection, filename)
                        else:
                            #We have a conflict remote file is newer than what
                            #we try to delete
                            self.logger.debug(
                                'Delete conflictLocal: %s' % filename)
                            self._download(webdavConnection, filename,
                                           None, time_delta)

                #What to do with new remote file
                for filename in set(remote_filenames) \
                                - set(lastsync_remote_filenames):
                    if not filename in local_filenames.keys():
                        self._download(webdavConnection, filename,
                                       None, time_delta)
                    else:
                        #Conflict : it s a new file so we haven't sync it yet
                        self.logger.debug('New conflictServer: %s' % filename)
                        self._conflictServer(webdavConnection,
                                             filename, time_delta,
                                             useAutoMerge)

                #What to do with new local file
                for filename in set(local_filenames) \
                                - set(lastsync_local_filenames):
                    if not filename in remote_filenames.keys():
                        self._upload(webdavConnection, filename,
                                     None, time_delta)
                    else:
                        #Conflict : it s a new file so we haven't sync it yet
                        self.logger.debug('New conflictLocal: %s' % filename)
                        self._conflictLocal(webdavConnection,
                                            filename, time_delta, useAutoMerge)

                #Check what's updated remotly
                rupdated = [filename for filename
                               in (set(remote_filenames).
                               intersection(lastsync_remote_filenames))
                               if remote_filenames[filename]
                                  != lastsync_remote_filenames[filename]]
                lupdated = [filename for filename
                               in (set(local_filenames).
                               intersection(lastsync_local_filenames))
                               if local_filenames[filename]
                                  != lastsync_local_filenames[filename]]
                for filename in set(rupdated) - set(lupdated):
                    self._download(webdavConnection, filename,
                                   None, time_delta)
                for filename in set(lupdated) - set(rupdated):
                    self._upload(webdavConnection, filename,
                                 None, time_delta)
                for filename in set(lupdated).intersection(rupdated):
                    if int(remote_filenames[filename] - time_delta) \
                         > int(local_filenames[filename]):
                        self.logger.debug(
                                'Updated conflictLocal: %s' % filename)
                        self._conflictLocal(webdavConnection, filename,
                                            time_delta, useAutoMerge)
                    elif int(remote_filenames[filename] - time_delta) \
                     < int(local_filenames[filename]):
                        self.logger.debug('Updated conflictServer: %s'
                                           % filename)
                        self._conflictServer(webdavConnection, filename,
                                             time_delta, useAutoMerge)
                    else:
                        self.logger.debug('Up to date: %s' % filename)

                #Build and write index
                self._write_index(webdavConnection, time_delta)

                #Un_lock the collection
                self._unlock(webdavConnection)
            except Exception, err:
                import traceback
                print traceback.format_exc()
                self.on_error.emit(unicode(err))
                self.logger.debug('Global sync error : %s' % unicode(err))

    def _conflictServer(self, webdavConnection, filename,
                        time_delta, useAutoMerge):
        '''Priority to local'''
        self.logger.debug('conflictServer: %s' % filename)
        lpath = os.path.join(self._localDataFolder, filename)
        cpath = os.path.join(self._localDataFolder,
                os.path.splitext(filename)[0] + '.Conflict.txt')
        bpath = os.path.join(self._localDataFolder, 'merge.sync',
                             filename)
        self._download(webdavConnection,
                       filename,
                       os.path.splitext(filename)[0] + '.Conflict.txt',
                       time_delta)

        #Test if it s a real conflict
        if md5util.md5sum(lpath) == md5util.md5sum(cpath):
            os.remove(cpath)
        else:
            if useAutoMerge and os.path.exists(bpath):
                self._mergeFiles(lpath, bpath, cpath)
                os.remove(cpath)
                self._upload(webdavConnection,
                      filename, filename, time_delta)
            else:
                #Else duplicate
                self._upload(webdavConnection, os.path.splitext(
                             filename)[0] + '.Conflict.txt', None, time_delta)

    def _mergeFiles(self, lpath, bpath, cpath):
        from merge3.merge3 import Merge3
        a = file(lpath, 'rt').readlines()
        try:
            base = file(bpath, 'rt').readlines()
        except:
            base = file(cpath, 'rt').readlines()
        b = file(cpath, 'rt').readlines()

        m3 = Merge3(base, a, b)
        with open(lpath, 'wb') as fh:
            fh.writelines(m3.merge())

    def _conflictLocal(self, webdavConnection, filename,
                        time_delta, useAutoMerge):
        '''Priority to server'''
        self.logger.debug('conflictLocal: %s', filename)
        lpath = os.path.join(self._localDataFolder, filename)
        cpath = os.path.join(self._localDataFolder,
                os.path.splitext(filename)[0] + '.Conflict.txt')
        bpath = os.path.join(self._localDataFolder, '.merge.sync',
                             filename)

        os.rename(lpath, cpath)
        self._download(webdavConnection,
                       filename,
                       filename,
                       time_delta)

        #Test if it s a real conflict
        if md5util.md5sum(lpath) == md5util.md5sum(cpath):
            os.remove(cpath)
        else:
            if useAutoMerge and os.path.exists(bpath):
                self._mergeFiles(lpath, bpath, cpath)
                os.remove(cpath)
                self._upload(webdavConnection,
                    filename, filename, time_delta)
            else:
                self._upload(webdavConnection, os.path.splitext(filename)[0] +
                             '.Conflict.txt', None, time_delta)

    def _get_lastsync_filenames(self):
        index = ({}, {})
        try:
            with open(
                    os.path.join(
                            self._localDataFolder, '.index.sync'), 'rb') as fh:
                index = json.load(fh)
        except (IOError, TypeError, ValueError), err:
            self.logger.debug(
                    'First sync detected or error: %s' % unicode(err))
        print index
        return index

    def _write_index(self, webdavConnection, time_delta):
        '''Generate index for the next sync and base for merge'''
        import shutil
        import glob
        index = (self._get_remote_filenames(webdavConnection),
                 self._get_local_filenames())
        with open(os.path.join(
            self._localDataFolder, '.index.sync'), 'wb') as fh:
            json.dump(index, fh)
            merge_dir = os.path.join(
              self._localDataFolder, '.merge.sync/')
            if os.path.exists(merge_dir):
                shutil.rmtree(merge_dir)

            os.makedirs(merge_dir)
            for filename in glob.glob(os.path.join(self._localDataFolder,
              '*.txt')):
                try:
                    if os.path.isfile(filename):
                        shutil.copy(filename,
                                    os.path.join(merge_dir,
                                                 os.path.basename(filename)))
                except IOError, err:
                    print err, 'filename:', filename, ' merge_dir:', merge_dir

    def _rm_remote_index(self,):
        '''Delete the remote index stored locally'''
        try:
            with open(os.path.join(
                    self._localDataFolder, '.index.sync'), 'rb') as fh:
                index = json.load(fh)
            with open(os.path.join(
                    self._localDataFolder, '.index.sync'), 'wb') as fh:
                json.dump(({}, index[1]), fh)
        except:
            raise

    def _move(self, webdavConnection, src, dst):
        '''Move/Rename a note on webdav'''
        webdavConnection.path = self._get_notes_path()
        resource = webdavConnection.addResource(src)
        resource.move(self.webdavHost + self._get_notes_path() + dst)

    def _upload(self, webdavConnection, local_filename,
                      remote_filename, time_delta):
        #TODO set modification time on local file as
        #"it s not possible on remote
        if not remote_filename:
            remote_filename = local_filename
        self.logger.debug('Upload %s to %s' %
                          (local_filename, remote_filename))
        webdavConnection.path = self._get_notes_path()
        resource = webdavConnection.addResource(remote_filename)
        lpath = os.path.join(self._localDataFolder, local_filename)
        with open(lpath, 'rb') as fh:
            resource.uploadFile(fh)
            mtime = time.mktime(resource.readStandardProperties()
                    .getLastModified()) - time_delta
            os.utime(lpath, (-1, mtime))

    def _download(self, webdavConnection, remote_filename,
                        local_filename, time_delta):
        if not local_filename:
            local_filename = remote_filename
        self.logger.debug('Download %s to %s' %
                          (remote_filename, local_filename))
        webdavConnection.path = self._get_notes_path() + remote_filename
        lpath = os.path.join(
                self._localDataFolder, getValidFilename(local_filename))
        webdavConnection.downloadFile(lpath)
        mtime = time.mktime(webdavConnection.readStandardProperties()
                            .getLastModified()) - time_delta
        os.utime(lpath, (-1, mtime))

    def _remote_delete(self, webdavConnection, filename):
        webdavConnection.path = self._get_notes_path()
        webdavConnection.deleteResource(filename)
        self.logger.debug('remote_delete: %s' % filename)

    def _local_delete(self, filename):
        os.remove(os.path.join(self._localDataFolder, filename))
        self.logger.debug('local_delete: %s' % filename)

    def _unlock(self, filename):
        #TODO
        pass

    def _get_notes_path(self):
        khtnotesPath = self.webdavBasePath
        if not khtnotesPath.endswith('/'):
            return khtnotesPath + '/' + self._remoteDataFolder + '/'
        else:
            return khtnotesPath + self._remoteDataFolder + '/'

    def _check_khtnotes_folder_and_lock(self, webdavConnection):
        '''Check that khtnotes folder exists on webdav'''
        try:
            khtnotesPath = self._get_notes_path()
            if not khtnotesPath in webdavConnection.listResources().keys():
                webdavConnection.addCollection(self._remoteDataFolder + '/')
                #So here it s a new share, and if have old index file
                #locally notes will be lose
                self._rm_remote_index()
            #TODO : Lock
        except Exception, err:
            self.logger.error(unicode(err))
            import traceback
            print traceback.format_exc()
            raise

    def _get_remote_filenames(self, webdavConnection):
        '''Check Remote Index'''
        webdavConnection.path = self._get_notes_path()
        index = dict([(basename(resource),
                        time.mktime(properties.getLastModified()))
                        for (resource, properties)
                        in webdavConnection.listResources().items()])
        try:
            del index['']
        except KeyError:
            pass

        try:
            del index['.index.sync']
        except KeyError:
            pass
        self.logger.debug('_get_remote_filenames: %s' % unicode(index))
        #Cleaning a bit for test:)
        #for filename in index.keys():
        #    self._remote_delete(webdavConnection, filename)
        #index = self._get_remote_filenames(webdavConnection)
        return index

    def _get_local_filenames(self):
        index = dict([(filename.decode('utf-8'),
                    round(os.path.getmtime(
                        os.path.join(
                            self._localDataFolder, filename.decode('utf-8')))))
                    for filename in os.listdir(self._localDataFolder)
                    if os.path.isfile(os.path.join(
                            self._localDataFolder, filename))])
        try:
            del index['.index.sync']
        except KeyError:
            pass

        self.logger.debug('_get_local_filenames: %s' % unicode(index))
        return index

    def _write(self, uid, data, timestamp=None):
        ''' Write the document to a file '''
        note = Note(uid=uid)
        note.write(data)
        if timestamp is not None:
                note.overwrite_timestamp()

    def _get_running(self):
        return self._running

    def _set_running(self, b):
        self._running = b
        self.on_running.emit()

    on_finished = Signal()
    on_error = Signal(unicode)
    on_running = Signal()
    running = Property(bool, _get_running, _set_running, notify=on_running)

if __name__ == '__main__':
    s = Sync()
    s.launch()
