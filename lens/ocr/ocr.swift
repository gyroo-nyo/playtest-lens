// Reads text in images with macOS Vision. Usage: lens-ocr <image>...
// One JSON object per image on stdout: {"file": ..., "lines": [{"text": ..., "x": ..., "y": ..., "w": ..., "h": ...}]}
// Boxes are 0..1 with the origin top-left (Vision's is bottom-left).
import Foundation
import Vision

for path in CommandLine.arguments.dropFirst() {
    var lines: [[String: Any]] = []
    let request = VNRecognizeTextRequest { req, _ in
        for case let obs as VNRecognizedTextObservation in req.results ?? [] {
            guard let top = obs.topCandidates(1).first else { continue }
            let b = obs.boundingBox
            lines.append(["text": top.string, "x": b.minX, "y": 1 - b.maxY, "w": b.width, "h": b.height])
        }
    }
    request.recognitionLevel = .accurate
    request.usesLanguageCorrection = false   // keep raw keys like MENU_START_TITLE as they are
    request.minimumTextHeight = 0.012        // the scoreboard strip is tiny next to the screen
    let handler = VNImageRequestHandler(url: URL(fileURLWithPath: path))
    try? handler.perform([request])
    let out: [String: Any] = ["file": path, "lines": lines]
    if let data = try? JSONSerialization.data(withJSONObject: out), let s = String(data: data, encoding: .utf8) {
        print(s)
    }
}
