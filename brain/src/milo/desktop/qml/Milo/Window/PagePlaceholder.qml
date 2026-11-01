import QtQuick
import Milo
import Milo.Controls

// Where a page goes whose QML isn't written yet: a calm note instead of a broken window.
Item {
    property string page: ""
    EmptyState {
        anchors.centerIn: parent
        width: Math.min(parent.width - 48, 360)
        icon: "sparkles"
        title: "This page is on its way."
        detail: "Ask Milo instead: he can do everything this page will show."
    }
}
