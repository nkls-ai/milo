import QtQuick
import "../../../src/milo/desktop/qml/Milo/Pages/wire.mjs" as Wire

// Lets test_qml_pages.py call Pages/wire.mjs from Python.
Item {
    function answer(question, choice) {
        try { return Wire.confirmAnswer(question, choice) } catch (e) { return null }
    }
}
