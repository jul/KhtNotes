import QtQuick 1.1
import com.nokia.meego 1.0
import com.nokia.extras 1.1
import 'components'
import 'common.js' as Common

PageStackWindow {
    id: appWindow

    initialPage: fileBrowserPage

    Harmattan_MainPage {
        id: fileBrowserPage
        objectName: 'fileBrowserPage'
    }

    
    ItemMenu {
        id: itemMenu
    }

    ToolBarLayout {
        id: mainTools
        visible: true

        ToolIcon {
            platformIconId: "toolbar-add" 
            onClicked: {Note.create();pageStack.push(Qt.createComponent(Qt.resolvedUrl("Harmattan_EditPage.qml")), {modified:'false'});
        }}

        ToolIcon {
            platformIconId: Sync.running ? 'toolbar-mediacontrol-stop' : 'toolbar-refresh';
            onClicked: Sync.launch();
                                            }
                                            
        ToolIcon {
            platformIconId: "toolbar-view-menu"
            onClicked: (myMenu.status === DialogStatus.Closed) ? myMenu.open() : myMenu.close()
        }
    }


    ToolBarLayout {
        id: commonTools
        visible: false
        ToolIcon {
            platformIconId: "toolbar-back"
            anchors.left: (parent === undefined) ? undefined : parent.left
            onClicked: pageStack.pop();
        }

        ToolIcon {
            platformIconId: "toolbar-view-menu"
            anchors.right: (parent === undefined) ? undefined : parent.right
            onClicked: (myMenu.status === DialogStatus.Closed) ? myMenu.open() : myMenu.close()
        }
    }


    Menu {
        id: myMenu
        visualParent: pageStack
        MenuLayout {
            MenuItem { text: qsTr("About"); onClicked: pushAbout()}
            MenuItem { text: qsTr("Preferences"); onClicked: pageStack.push(Qt.createComponent(Qt.resolvedUrl("Harmattan_SettingsPage.qml"))); }
            MenuItem { text: qsTr("Report a bug");onClicked: {
                         Qt.openUrlExternally('https://github.com/khertan/KhtNotes/issues/new');
                    }
            }
        }
    }

    InfoBanner{
                      id:notYetAvailableBanner
                      text: 'This feature is not yet available'
                      timerShowTime: 5000
                      timerEnabled:true
                      anchors.top: parent.top
                      anchors.topMargin: 60
                      anchors.horizontalCenter: parent.horizontalCenter
                 }

    InfoBanner{
                      id:errorBanner
                      text: 'An error occur while creating new folder'
                      timerShowTime: 15000
                      timerEnabled:true
                      anchors.top: parent.top
                      anchors.topMargin: 60
                      anchors.horizontalCenter: parent.horizontalCenter
                 }

    function onError(errMsg) {
        errorEditBanner.text = errMsg;
        errorEditBanner.show();
    }

    InfoBanner{
                      id:errorEditBanner
                      text: ''
                      timerShowTime: 15000
                      timerEnabled:true
                      anchors.top: parent.top
                      anchors.topMargin: 60
                      anchors.horizontalCenter: parent.horizontalCenter
                 }

   showStatusBar: true

    QueryDialog {
        property string uuid
        id: deleteQueryDialog
        icon: Qt.resolvedUrl('../icons/khtnotes.png')
        titleText: "Delete"
        message: "Are you sure you want to delete this note ?"
        acceptButtonText: qsTr("Delete")
        rejectButtonText: qsTr("Cancel")
        onAccepted: {
                Note.rm(uuid);
                fileBrowserPage.refresh();
        }
    }

    function pushAbout() {
        pageStack.push(Qt.createComponent(Qt.resolvedUrl("components/AboutPage.qml")),
             {
                          title : 'KhtNotes ' + __version__,
                          iconSource: Qt.resolvedUrl('../icons/khtnotes.png'),
                          slogan : 'Notes in your own cloud !',
                          text : 
                             'A note taking application with sync with owncloud for MeeGo and Harmattan.' +
                             '<br>Web Site : http://khertan.net/khtnotes' +
                             '<br><br>By Benoît HERVIER (Khertan)' +
                             '<br><b>Licenced under GPLv3</b>' +
                             '<br><br><b>Changelog : </b><br>' +
                             __upgrade__ +
                             '<br><br><b>Thanks to : </b>' +
                             '<br>Radek Novacek' 
                             
             }
             );
    }

    //State used to detect when we should refresh view
    states: [
            State {
                        name: "fullsize-visible"
                        when: platformWindow.viewMode === WindowState.Fullsize && platformWindow.visible
                        StateChangeScript {
                                 script: {
                                 console.log('objectName:'+pageStack.currentPage.objectName);
                                 if (pageStack.currentPage.objectName === 'fileBrowserPage') {
                                 	pageStack.currentPage.refresh();}
                                 }       }
                  }
            ]
}
