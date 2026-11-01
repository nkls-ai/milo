import QtQuick
import QtQuick.Layouts
import Milo
import Milo.Controls

// A service Milo uses: its name and plan, what he uses it for, who he is signed in as, and whether it works — an
// icon and a word, never colour alone. `account` is a usage event's accounts entry.
RowLayout {
    id: row
    property var account: ({})
    readonly property var badge: ({
        ok: ["checkmark.circle", "Signed in", Tones.done],
        signed_out: ["xmark.circle", "Signed out", Tones.failed],
        unknown: ["questionmark.circle", "Can't tell", Tones.running],
        local: ["lock", "Private", Theme.primary]
    })[account.state] || ["questionmark.circle", "Can't tell", Tones.running]

    Layout.fillWidth: true
    spacing: 12
    Accessible.role: Accessible.StaticText
    Accessible.name: account.service + ", " + badge[1]

    Rectangle {
        Layout.alignment: Qt.AlignTop
        implicitWidth: 30
        implicitHeight: 30
        radius: 15
        color: Tones.fade(Theme.primary, 0.12)
        Icon {
            anchors.centerIn: parent
            // "This Mac" is the brain's word for the computer Milo runs on.
            name: /^This (Mac|PC|computer)$/.test(row.account.service) ? "laptop"
                : row.account.service === "ElevenLabs" ? "waveform" : "person"
            size: 14
            color: Theme.primary
        }
    }
    ColumnLayout {
        Layout.fillWidth: true
        spacing: 3
        RowLayout {
            spacing: 6
            MiloText { text: row.account.service || ""; size: 13.5; weight: "semibold"; rounded: true }
            Pill { visible: !!row.account.plan; text: row.account.plan || ""; filled: true }
        }
        MiloText { Layout.fillWidth: true; text: (row.account.uses || []).join(" · "); size: 11.5; tone: 0.6 }
        MiloText {
            Layout.fillWidth: true
            visible: text !== ""
            text: [row.account.who, row.account.detail].filter(s => !!s).join(" · ")
            size: 11
            tone: 0.45
            wrapMode: Text.WordWrap
        }
    }
    Row {
        Layout.alignment: Qt.AlignTop
        spacing: 4
        Icon { anchors.verticalCenter: parent.verticalCenter; name: row.badge[0]; size: 13; color: row.badge[2] }
        MiloText { text: row.badge[1]; size: 11; weight: "semibold"; rounded: true; tone: 0.7 }
    }
}
