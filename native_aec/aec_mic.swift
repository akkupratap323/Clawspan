// aec_mic — captures mic audio with Apple's VoiceProcessingIO AEC
// applied (same stack FaceTime/Zoom use), resamples to 16 kHz mono
// Int16 PCM, and writes raw samples to stdout.
//
// Build:  swiftc -O aec_mic.swift -o aec_mic
// Run:    ./aec_mic > /tmp/mic.pcm
//         ./aec_mic | your_stt_pipeline
//
// Stderr is used for status/errors. Stdout is strictly raw PCM.

import AVFoundation
import Darwin

// MARK: - Config

let targetSampleRate: Double = 16_000
let targetChannels: AVAudioChannelCount = 1

// MARK: - Logging (stderr only — stdout is reserved for PCM)

func logErr(_ msg: String) {
    FileHandle.standardError.write((msg + "\n").data(using: .utf8) ?? Data())
}

// MARK: - Engine setup

// Post-conversion linear gain. VPIO output tends to sit low; ~4x (+12 dB)
// brings it close to pre-AEC levels. Clipped to Int16 range.
let postGain: Float = 8.0

let engine = AVAudioEngine()
let input = engine.inputNode

// Enable VoiceProcessing (AEC + AGC + NS). Available on macOS 10.15+/iOS 13+.
do {
    try input.setVoiceProcessingEnabled(true)
    // Keep AGC on — it normalises voice loudness. Ducking stays off.
    input.isVoiceProcessingAGCEnabled = true
    input.isVoiceProcessingBypassed = false
    logErr("[aec_mic] VPIO on, AGC on, postGain=\(postGain)x")
} catch {
    logErr("[aec_mic] setVoiceProcessingEnabled failed: \(error) — continuing without AEC")
}


// After VPIO is enabled, inputFormat reports a bogus channel count (e.g. 9ch)
// even though VPIO delivers mono. Use an explicit mono Float32 tap format at
// the hardware sample rate — AVAudioEngine handles the channel downmix.
let hwRaw = input.inputFormat(forBus: 0)
logErr("[aec_mic] hw reports: \(hwRaw.sampleRate) Hz, \(hwRaw.channelCount) ch")
guard let tapFormat = AVAudioFormat(
    commonFormat: .pcmFormatFloat32,
    sampleRate: hwRaw.sampleRate,
    channels: 1,
    interleaved: true
) else {
    logErr("[aec_mic] failed to build tap format")
    exit(2)
}
logErr("[aec_mic] tap format: \(tapFormat.sampleRate) Hz, \(tapFormat.channelCount) ch")

guard let targetFormat = AVAudioFormat(
    commonFormat: .pcmFormatInt16,
    sampleRate: targetSampleRate,
    channels: targetChannels,
    interleaved: true
) else {
    logErr("[aec_mic] failed to build target format")
    exit(2)
}

guard let converter = AVAudioConverter(from: tapFormat, to: targetFormat) else {
    logErr("[aec_mic] failed to build converter from \(tapFormat) to \(targetFormat)")
    exit(3)
}

let stdout = FileHandle.standardOutput

// MARK: - Tap: convert each chunk to 16 kHz Int16, write to stdout

input.installTap(onBus: 0, bufferSize: 1024, format: tapFormat) { buffer, _ in
    let ratio = targetSampleRate / tapFormat.sampleRate
    let outCapacity = AVAudioFrameCount(Double(buffer.frameLength) * ratio) + 32
    guard let outBuf = AVAudioPCMBuffer(
        pcmFormat: targetFormat,
        frameCapacity: outCapacity
    ) else { return }

    var consumed = false
    var error: NSError?
    let status = converter.convert(to: outBuf, error: &error) { _, outStatus in
        if consumed {
            outStatus.pointee = .noDataNow
            return nil
        }
        consumed = true
        outStatus.pointee = .haveData
        return buffer
    }

    if status == .error {
        logErr("[aec_mic] convert error: \(error?.localizedDescription ?? "?")")
        return
    }

    let frames = Int(outBuf.frameLength)
    guard frames > 0, let ch = outBuf.int16ChannelData?[0] else { return }
    if postGain != 1.0 {
        for i in 0..<frames {
            let boosted = Float(ch[i]) * postGain
            if boosted > 32767 { ch[i] = 32767 }
            else if boosted < -32768 { ch[i] = -32768 }
            else { ch[i] = Int16(boosted) }
        }
    }
    let bytes = frames * MemoryLayout<Int16>.size
    let data = Data(bytes: ch, count: bytes)
    stdout.write(data)
}

// MARK: - Signal handling (clean shutdown on SIGINT/SIGTERM)

let sigSource = DispatchSource.makeSignalSource(signal: SIGINT, queue: .main)
sigSource.setEventHandler {
    logErr("[aec_mic] SIGINT — stopping")
    engine.stop()
    exit(0)
}
sigSource.resume()
signal(SIGINT, SIG_IGN)

let sigTerm = DispatchSource.makeSignalSource(signal: SIGTERM, queue: .main)
sigTerm.setEventHandler {
    logErr("[aec_mic] SIGTERM — stopping")
    engine.stop()
    exit(0)
}
sigTerm.resume()
signal(SIGTERM, SIG_IGN)

// MARK: - Start

do {
    try engine.start()
    logErr("[aec_mic] running — 16 kHz Int16 mono PCM on stdout (VPIO AEC on)")
} catch {
    logErr("[aec_mic] engine.start failed: \(error)")
    exit(4)
}

// Keep main thread alive; the tap runs on an internal audio thread.
RunLoop.main.run()
