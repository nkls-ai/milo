import AppKit
import SwiftUI

/// The colours and motion of the active skin, so every surface around Milo matches him: the bubble, the windows,
/// the setup scenes, the overlays. One per `CharacterStyle`; it changes live with `[ui] character`.
///
///     Theme.for(.dragon).primary            // SwiftUI
///     Theme.for(.dragon).appKit.primary     // AppKit (NSColor), for panels and layers
///     @Environment(\.miloTheme) var theme   // inside a view under `.themed(by: model)`
///     model.theme                           // from a MiloModel
///
/// Every colour adapts to light and dark mode by itself.
public struct Theme: Equatable, Sendable {
    public let style: CharacterStyle
    public let appKit: ThemeColors
    public let motion: ThemeMotion

    /// The skin's main colour: buttons, selection, the thread of a task, the cursor.
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

    public static func `for`(_ style: CharacterStyle) -> Theme {
        switch style {
        case .pip: pip
        case .classic: classic
        case .dragon: dragon
        case .kit: kit
        case .glow: glow
        }
    }

    /// Lavender and airy: soft springs, a gentle float.
    static let pip = Theme(style: .pip, colors: .init(
        primary: (rgb(0.42, 0.36, 0.75), rgb(0.72, 0.68, 0.95)),
        tint: (rgb(0.957, 0.949, 0.996), rgb(0.118, 0.106, 0.200)),
        accent: (rgb(0.90, 0.56, 0.18), rgb(0.98, 0.72, 0.38)),
        ink: (rgb(0.17, 0.14, 0.33), rgb(0.93, 0.92, 1.0)),
        glow: (rgb(0.80, 0.76, 0.98), rgb(0.52, 0.46, 0.90))),
        motion: ThemeMotion(response: 0.5, damping: 0.78, bob: 1))

    /// The purple robot: a steady, friendly bounce.
    static let classic = Theme(style: .classic, colors: .init(
        primary: (rgb(0.45, 0.22, 0.93), rgb(0.71, 0.47, 1.0)),
        tint: (rgb(0.962, 0.945, 1.0), rgb(0.105, 0.090, 0.240)),
        accent: (rgb(0.08, 0.56, 0.74), rgb(0.36, 0.86, 1.0)),
        ink: (rgb(0.12, 0.10, 0.29), rgb(0.95, 0.93, 1.0)),
        glow: (rgb(0.78, 0.66, 1.0), rgb(0.55, 0.36, 0.98))),
        motion: ThemeMotion(response: 0.42, damping: 0.7, bob: 1))

    /// Teal with ember sparks: quick, bouncy springs.
    static let dragon = Theme(style: .dragon, colors: .init(
        primary: (rgb(0.13, 0.50, 0.40), rgb(0.50, 0.84, 0.66)),
        tint: (rgb(0.937, 0.976, 0.953), rgb(0.075, 0.145, 0.125)),
        accent: (rgb(0.90, 0.40, 0.33), rgb(1.0, 0.60, 0.48)),
        ink: (rgb(0.08, 0.21, 0.18), rgb(0.90, 0.98, 0.94)),
        glow: (rgb(1.0, 0.72, 0.30), rgb(1.0, 0.66, 0.26))),
        motion: ThemeMotion(response: 0.38, damping: 0.58, bob: 1.2))

    /// Warm paper and fox orange: crisp, folded, barely any overshoot.
    static let kit = Theme(style: .kit, colors: .init(
        primary: (rgb(0.74, 0.36, 0.14), rgb(0.95, 0.62, 0.38)),
        tint: (rgb(0.988, 0.965, 0.925), rgb(0.145, 0.118, 0.102)),
        accent: (rgb(0.24, 0.20, 0.19), rgb(0.97, 0.92, 0.85)),
        ink: (rgb(0.22, 0.17, 0.15), rgb(0.97, 0.92, 0.85)),
        glow: (rgb(0.97, 0.80, 0.62), rgb(0.85, 0.48, 0.24))),
        motion: ThemeMotion(response: 0.28, damping: 0.86, bob: 0.6))

    /// Lantern amber in a night-blue sky: slow, floaty springs.
    static let glow = Theme(style: .glow, colors: .init(
        primary: (rgb(0.78, 0.48, 0.10), rgb(1.0, 0.80, 0.45)),
        tint: (rgb(0.988, 0.973, 0.925), rgb(0.075, 0.094, 0.188)),
        accent: (rgb(0.22, 0.30, 0.58), rgb(0.58, 0.70, 0.98)),
        ink: (rgb(0.20, 0.17, 0.30), rgb(0.96, 0.94, 0.88)),
        glow: (rgb(1.0, 0.82, 0.48), rgb(1.0, 0.78, 0.40))),
        motion: ThemeMotion(response: 0.7, damping: 0.82, bob: 1.4))

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
        // At night a card is the skin's own night paper, a little lighter.
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

/// How a skin moves. Springs only, never linear tweens.
public struct ThemeMotion: Equatable, Sendable {
    /// Spring response in seconds: lower is quicker.
    public let response: Double
    /// Spring damping fraction: lower bounces more.
    public let damping: Double
    /// How far decorative things bob and float, 1 for Pip.
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
    static let defaultValue = Theme.for(.pip)
}

extension EnvironmentValues {
    /// The active skin's theme. Set by `.themed(by:)`.
    public var miloTheme: Theme {
        get { self[ThemeKey.self] }
        set { self[ThemeKey.self] = newValue }
    }
}

extension MiloModel {
    /// The theme of the skin he wears now.
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
