import SwiftUI

struct KitFigure: Skin {
    var look: SkinLook
    static func idleLoop(_ look: SkinLook) -> Loop? { PipFigure.idleLoop(look) }
    var body: some View { PipFigure(look: look) }
}
