import QtQuick
import Milo
import Milo.Controls

// A settings card with one setting's choices under its heading; hidden while the brain hasn't reported it.
// `choices` are [{value, label}] (SettingsPage.choices); emits chosen(value).
Card {
    id: card
    property var setting: null
    property var choices: []
    property string icon
    property string title
    property string detail
    signal chosen(var value)

    visible: !!setting
    objectName: setting ? setting.section + "." + setting.key : ""

    CardHeading { icon: card.icon; title: card.title; detail: card.detail }
    ChoiceList {
        name: card.title
        choices: card.choices
        selected: card.setting ? card.setting.value : null
        onChosen: value => card.chosen(value)
    }
}
