#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# Copyright (c) 2011 Benoit HERVIER <khertan@khertan.net>
# Licenced under GPLv3

## This program is free software; you can redistribute it and/or modify
## it under the terms of the GNU General Public License as published
## by the Free Software Foundation; version 3 only.
##
## This program is distributed in the hope that it will be useful,
## but WITHOUT ANY WARRANTY; without even the implied warranty of
## MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
## GNU General Public License for more details.

import os
import urllib2
import urllib
import json
import threading
from PySide.QtCore import QObject, Slot, Signal, Property
from note import Note
from settings import Settings

class Sync(QObject):
  '''Sync class'''

  def __init__(self,):
    QObject.__init__(self)
    self._running = False

  @Slot()
  def launch(self):
    ''' Sync the notes in a thread'''
    if not self._get_running():
        self._set_running(True)
        self.thread = threading.Thread(target=self._sync)
        self.thread.start()

  def _get_data(self):
    
    data = {}
    index = {}    
    notes = []
    delnotes = []
    
    for root, dirs, files in os.walk(Note.NOTESPATH):
        notes = [Note(uid=file) for file in files]  
        
    for root, dirs, files in os.walk(Note.DELETEDNOTESPATH):
        delnotes = [Note(uid=file) for file in files]  
        
    for note in notes:
        index[note.uuid] = {'timestamp':note.timestamp,
                            'title':note.title,}
        data[note.uuid] = json.dumps({"entry-id":note.uuid,"entry-content":note.data})
    for note in delnotes:
        index[note.uuid] = {'timestamp':'0',
                            'title':note.title,}                            
        data[note.uuid] = json.dumps({"entry-id":note.uuid,"entry-content":''})
        
    data['index'] = json.dumps(index)
    return data
        
  def _sync(self):
    ''' Sync the notes'''
    
    try:
        settings = Settings()

        passman = urllib2.HTTPPasswordMgrWithDefaultRealm()
        passman.add_password(None, settings.syncUrl, settings.syncLogin, settings.syncPassword)
        authhandler = urllib2.HTTPBasicAuthHandler(passman)
        opener = urllib2.build_opener(authhandler)    
        urllib2.install_opener(opener)

        local_data = self._get_data()
        response = urllib2.urlopen(settings.syncUrl, urllib.urlencode(local_data))

        remote_data = json.load(response)

        remote_index = remote_data['index']
        remote_entries = remote_data['entries']
        
        for rindex in remote_index:
            #remote_index = json.loads(rindex)
            ridata = remote_index[rindex]
            
            if rindex in local_data.keys():
                if ridata['timestamp'] == 0 : #Remote entry has been deleted, remove the local too
                    Note(rindex).rm()
                elif os.path.exists(os.path.join(Note.DELETEDNOTESPATH,rindex)): #Local entry has been deleted, remove local entry too
                    pass
                elif ridata['timestamp'] > local_data[rindex]:# Remote entry is newer, get it
                    note = Note(uid=rindex)
                    print 'DEBUG remote data keys:', remote_entries[rindex]
                    note.write(remote_entries[rindex]['entry-content'])
                    note.overwrite_timestamp(float(ridata['timestamp']))
                elif ridata['timestamp'] == local_data[rindex]:# Local entry is already the latest, don't get it
                    pass
                else : # Local entry is newer, don't get it
                    pass
            else:    # Else we store it
                note = Note(uid=rindex)
                print 'DEBUG remote data keys:', remote_entries[rindex]
                note.write(remote_entries[rindex]['entry-content'])
                print int(ridata['timestamp'])
                note.overwrite_timestamp(float(ridata['timestamp']))
 

    except Exception, e:
        import traceback
        traceback.print_exc()
        print type(e), ':', e
        self.on_error.emit(str(e))
    
    self._set_running(False)
                  
  def _write(self, uid, data, timestamp=None):
    ''' Write the document to a file '''
    note = Note(uid=uid)
    note.write(data)
    if timestamp != None:
        note.overwrite_timestamp()

  def _get_running(self):
    return self._running
  def _set_running(self, b):
    self._running = b
    self.on_running.emit()
 
  on_error = Signal(unicode)
  on_running = Signal()
  running = Property(bool, _get_running, _set_running, notify=on_running) 

if __name__ == '__main__':
  s = Sync()
  s.launch()   
