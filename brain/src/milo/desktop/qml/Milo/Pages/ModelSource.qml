import QtQuick
import QtQuick.Layouts
import Milo
import Milo.Controls

// Where an OpenAI-style talking model runs, for Setup's Connections & models: a preset (Ollama, LM Studio, OpenAI,
// OpenRouter, Groq, Custom) fills the address and the key's file; a server on this computer is found by itself
// and its models offered; a hosted one takes a pasted key; Test asks for one short reply.
//
// The presets come from the backend (milo/adapters/harness/openai_presets.py), never from here.
// Inputs: backend (SetupBackend or null). State the page reads and saves: endpoint, model, keyRef, key (pasted,
// cleared after a save). load(selection) starts from what is saved.
ColumnLayout {
    id: source
    property QtObject backend: null
    property alias endpoint: endpointField.text
    property alias model: modelField.text
    property alias keyRef: keyRefField.text
    property alias key: keyField.text

    readonly property var presets: backend ? backend.presets : []
    readonly property string presetId: backend ? backend.presetFor(endpoint) : "custom"
    readonly property var preset: presets.find(p => p.id === presetId) || ({ id: "custom", label: "Custom", local: false, base_url: "", key_ref: "", keys_url: "" })
    readonly property var found: backend ? backend.detected.find(d => d.id === presetId) : undefined
    readonly property var listing: backend ? backend.models : ({ endpoint: "", names: [], error: "", busy: false })
    readonly property var names: listing.endpoint === endpoint.trim() ? listing.names : []
    // Why the list is empty, unless the line about the local server already says it.
    readonly property string listError: listing.endpoint === endpoint.trim() && !(preset.local && !found) ? listing.error : ""
    // At most eight of its models: those that contain what is typed, or all once a whole name is chosen.
    readonly property var suggestions: {
        const typed = names.indexOf(model.trim()) >= 0 ? "" : model.trim().toLowerCase()
        const hits = names.filter(n => typed === "" || n.toLowerCase().indexOf(typed) >= 0)
        return (hits.length ? hits : names).slice(0, 8)
    }
    readonly property bool keySaved: backend && keyRef.trim() !== "" ? backend.keySaved(keyRef.trim()) : false
    readonly property var result: backend ? backend.testResult : ({ busy: false, ok: false, ms: 0, text: "" })

    function choice() { return { endpoint: endpoint.trim(), model: model.trim(), keyRef: keyRef.trim(), key: key } }
    function load(selection) {
        endpoint = selection.endpoint || ""
        model = selection.model || ""
        keyRef = selection.keyRef || ""
        key = ""
    }
    function choose(id) {
        const p = presets.find(x => x.id === id)
        if (!p) return
        if (p.id !== "custom") endpoint = p.base_url
        else if (presetId !== "custom") endpoint = ""
        keyRef = p.key_ref
        model = p.model || ""
        list()
    }
    // Lists the models where it can without asking: a local server, or a hosted one with a key.
    function list() {
        if (backend && endpoint.trim() !== "" && (preset.local || key !== "" || keySaved)) backend.fetchModels(choice())
    }

    Layout.fillWidth: true
    spacing: 10

    MiloSegmented {
        objectName: "presets"
        visible: source.presets.length > 0
        name: "Where the model runs"
        options: source.presets.map(p => ({ value: p.id, label: p.label }))
        current: source.presetId
        onPicked: value => source.choose(value)
    }

    // ---- a server on this computer: found, or how to start it
    RowLayout {
        visible: source.preset.local
        Layout.fillWidth: true
        spacing: 8
        Rectangle {
            implicitWidth: 8
            implicitHeight: 8
            radius: 4
            color: source.found ? Tones.done : Tones.fade(Theme.ink, 0.3)
        }
        MiloText {
            objectName: "found"
            Layout.fillWidth: true
            text: source.found
                  ? "Found " + source.preset.label + " on this computer"
                    + (source.found.models.length === 1 ? " with 1 model." : " with " + source.found.models.length + " models.")
                  : source.preset.label + " isn't running on this computer. Start it, then look again."
            size: Theme.type.caption
            tone: 0.75
            wrapMode: Text.WordWrap
        }
        MiloButton {
            objectName: "lookAgain"
            text: "Look again"
            kind: "quiet"
            size: "small"
            enabled: !!source.backend
            onClicked: { source.backend.detect(); source.list() }
        }
    }

    LabeledField {
        id: endpointField
        objectName: "endpoint"
        label: "API base URL"
        placeholder: "http://localhost:11434/v1 or your provider's API base URL"
        onEditingDone: source.list()
    }

    // ---- the model, with the server's own as quick picks
    LabeledField {
        id: modelField
        objectName: "model"
        label: "Model"
        placeholder: source.names.length ? "Type to filter, or pick one below" : "Model name from your server or provider"
    }
    Flow {
        Layout.fillWidth: true
        visible: source.suggestions.length > 0 || source.listing.busy || source.listError !== ""
        spacing: 6
        Spinner { visible: source.listing.busy; size: 14 }
        Repeater {
            model: source.suggestions
            MiloButton {
                required property string modelData
                objectName: "model:" + modelData
                text: modelData
                size: "small"
                kind: modelData === source.model.trim() ? "secondary" : "quiet"
                onClicked: source.model = modelData
            }
        }
        MiloText {
            visible: source.names.length > source.suggestions.length
            text: "and " + (source.names.length - source.suggestions.length) + " more"
            size: Theme.type.caption
            tone: 0.5
        }
        MiloText {
            objectName: "modelsError"
            visible: source.listError !== ""
            width: parent.width
            text: source.listError
            size: Theme.type.caption
            ink: Tones.failed
            wrapMode: Text.WordWrap
        }
    }

    // ---- the key, for a hosted API
    ColumnLayout {
        visible: !source.preset.local
        Layout.fillWidth: true
        spacing: 4
        MiloText { text: "API key"; size: Theme.type.caption; weight: "medium"; tone: 0.7 }
        RowLayout {
            Layout.fillWidth: true
            spacing: 8
            SecretField {
                id: keyField
                objectName: "key"
                Layout.fillWidth: true
                placeholder: source.keySaved ? "Saved. Paste a new key to replace it." : "Paste your key here"
                onAccepted: source.list()
            }
            MiloButton {
                objectName: "listModels"
                text: "List models"
                kind: "quiet"
                size: "small"
                enabled: !!source.backend && source.endpoint.trim() !== "" && (source.key !== "" || source.keySaved)
                onClicked: source.list()
            }
        }
        MiloText {
            Layout.fillWidth: true
            text: (source.keyRef.trim() ? "Saved alone in Milo/secrets/" + source.keyRef.trim() + ", never in config.toml." : "")
                  + (source.preset.keys_url ? " Make a key at " + source.preset.keys_url : "")
            size: Theme.type.caption
            tone: 0.55
            wrapMode: Text.WordWrap
        }
        LabeledField {
            id: keyRefField
            objectName: "keyRef"
            visible: source.preset.id === "custom"
            label: "Secret file name"
            placeholder: "provider.key — file name only; empty for a local server"
        }
    }

    // ---- Test: one short reply
    RowLayout {
        Layout.fillWidth: true
        spacing: 10
        MiloButton {
            objectName: "test"
            text: "Test"
            kind: "secondary"
            iconName: "bolt"
            enabled: !!source.backend && !source.result.busy && source.endpoint.trim() !== "" && source.model.trim() !== ""
            onClicked: source.backend.test(source.choice())
        }
        Spinner { visible: source.result.busy; size: 14 }
        Icon {
            visible: !source.result.busy && source.result.text !== ""
            name: source.result.ok ? "checkmark.circle" : "exclamationmark.triangle"
            size: 14
            color: source.result.ok ? Tones.done : Tones.failed
        }
        MiloText {
            objectName: "testResult"
            Layout.fillWidth: true
            text: source.result.text
            size: Theme.type.caption
            ink: source.result.busy ? Theme.ink : source.result.ok ? Tones.done : Tones.failed
            tone: source.result.busy ? 0.6 : 1
            wrapMode: Text.WordWrap
        }
    }
}
