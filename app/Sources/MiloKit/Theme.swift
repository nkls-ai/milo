import AppKit
import SwiftUI

/// Milo's colours and motion, so every surface around him matches him: the bubble, the windows, the setup
/// scenes, the overlays. Taken from the wren himself: lavender feathers, the marigold scarf.
///
///     Theme.for(.milo).primary              // SwiftUI
///     Theme.for(.milo).appKit.primary       // AppKit (NSColor), for panels and layers
///     @Environment(\.miloTheme) var theme   // inside a view under `.themed(by: model)`
///     model.theme                           // from a MiloModel
///
/// Every colour adapts to light and dark mode by itself.
public struct Theme: Equatable, Sendable {
    public let style: CharacterStyle
    public let appKit: ThemeColors
    public let motion: ThemeMotion

    /// Milo's main colour: buttons, selection, the thread of a task, the cursor.
    public var primary: Color { Color(nsColor: appKit.primary) }
    /// A soft wash of it: window paper and selected backgrounds.
    public var tint: Color { Color(nsColor: appKit.tint) }
    /// A second colour that pops against `primary`: badges, sparks, the "new" dot.
    public var accent: Color { Color(nsColor: appKit.accent) }
    /// Text and line work on `tint`.
    public var ink: Color { Color(nsColor: appKit.ink) }
    /// Light around Milo: halos, highlights, the glow behind a check mark.
    public var glow: Color { Color(nsColor: appKit.glow) }
    /// Text on `primary`.
    public var onPrimary: Color { Color(nsColor: appKit.onPrimary) }
    /// Cards and fields on `tint`.
    public var card: Color { Color(nsColor: appKit.card) }
    /// Hairlines and borders.
    public var rule: Color { Color(nsColor: appKit.rule) }

    public static func `for`(_ style: CharacterStyle) -> Theme { milo }

    /// The wren's own colours: lavender feathers, a marigold scarf, cream paper. Springs a little lively,
    /// like his hops.
    static let milo = Theme(style: .milo, colors: .init(
        primary: (rgb(0.37, 0.31, 0.64), rgb(0.71, 0.66, 0.94)),
        tint: (rgb(0.961, 0.949, 0.996), rgb(0.118, 0.106, 0.200)),
        accent: (rgb(0.79, 0.52, 0.15), rgb(0.94, 0.71, 0.29)),
        ink: (rgb(0.17, 0.14, 0.33), rgb(0.94, 0.93, 1.0)),
        glow: (rgb(0.78, 0.74, 0.94), rgb(0.50, 0.44, 0.82))),
        motion: ThemeMotion(response: 0.45, damping: 0.74, bob: 1))

    private init(style: CharacterStyle, colors: ThemeColors, motion: ThemeMotion) {
        self.style = style
        appKit = colors
        self.motion = motion
    }

    private static func rgb(_ r: CGFloat, _ g: CGFloat, _ b: CGFloat) -> NSColor {
        NSColor(srgbRed: r, green: g, blue: b, alpha: 1)
    }

    public static func == (a: Theme, b: Theme) -> Bool { a.style == b.style }
}

/// A theme's colours as NSColor, each with a light and a dark variant that AppKit picks by appearance.
public struct ThemeColors: @unchecked Sendable {
    public let primary, tint, accent, ink, glow, onPrimary, card, rule: NSColor

    init(primary: (NSColor, NSColor), tint: (NSColor, NSColor), accent: (NSColor, NSColor), ink: (NSColor, NSColor),
         glow: (NSColor, NSColor)) {
        self.primary = Self.dynamic(primary)
        self.tint = Self.dynamic(tint)
        self.accent = Self.dynamic(accent)
        self.ink = Self.dynamic(ink)
        self.glow = Self.dynamic(glow)
        // White on the deep light-mode primary, the dark paper on the bright dark-mode one.
        onPrimary = Self.dynamic((.white, tint.1))
        // At night a card is Milo's own night paper, a little lighter.
        let night = tint.1.blended(withFraction: 0.08, of: .white) ?? tint.1
        card = Self.dynamic((NSColor.white.withAlphaComponent(0.92), night))
        rule = Self.dynamic((primary.0.withAlphaComponent(0.14), NSColor.white.withAlphaComponent(0.10)))
    }

    static func dynamic(_ pair: (light: NSColor, dark: NSColor)) -> NSColor {
        NSColor(name: nil) { appearance in
            appearance.bestMatch(from: [.darkAqua, .aqua]) == .darkAqua ? pair.dark : pair.light
        }
    }
}

/// How Milo moves. Springs only, never linear tweens.
public struct ThemeMotion: Equatable, Sendable {
    /// Spring response in seconds: lower is quicker.
    public let response: Double
    /// Spring damping fraction: lower bounces more.
    public let damping: Double
    /// How far decorative things bob and float.
    public let bob: Double

    /// For things that appear, move or change.
    public var spring: Animation { .spring(response: response, dampingFraction: damping) }
    /// Slower and calmer, for large surfaces and colour changes.
    public var gentle: Animation { .spring(response: response * 1.6, dampingFraction: min(1, damping + 0.15)) }

    /// `spring`, or a short fade when the user asked macOS to reduce motion.
    public func animation(reduced: Bool) -> Animation {
        reduced ? .easeOut(duration: 0.18) : spring
    }
}

private struct ThemeKey: EnvironmentKey {
    static let defaultValue = Theme.milo
}

extension EnvironmentValues {
    /// Milo's theme. Set by `.themed(by:)`.
    public var miloTheme: Theme {
        get { self[ThemeKey.self] }
        set { self[ThemeKey.self] = newValue }
    }
}

extension MiloModel {
    /// His theme.
    public var theme: Theme { Theme.for(character) }
}

extension View {
    /// Puts `model.theme` in the environment and follows `[ui] character` live.
    public func themed(by model: MiloModel) -> some View {
        modifier(Themed(model: model))
    }
}

private struct Themed: ViewModifier {
    @ObservedObject var model: MiloModel

    func body(content: Content) -> some View {
        content
            .environment(\.miloTheme, model.theme)
            .tint(model.theme.primary)
    }
}
