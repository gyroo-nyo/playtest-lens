# Reads text in images with Windows' built-in OCR (Windows.Media.Ocr; free and offline). The Windows twin of ocr.swift.
# Usage: powershell -NoProfile -ExecutionPolicy Bypass -File ocr.ps1 <image>...
# One JSON object per image on stdout: {"file": ..., "lines": [{"text": ..., "x": ..., "y": ..., "w": ..., "h": ...}]}
# Boxes are 0..1 with the origin top-left. Needs Windows PowerShell 5.1 (powershell.exe), which loads WinRT types.
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [Text.Encoding]::UTF8
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$null = [Windows.Storage.StorageFile, Windows.Storage, ContentType = WindowsRuntime]
$null = [Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType = WindowsRuntime]
$null = [Windows.Graphics.Imaging.BitmapDecoder, Windows.Graphics, ContentType = WindowsRuntime]

# WinRT calls are async; this turns one into a .NET task and waits for it.
$asTask = [System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
    $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' } | Select-Object -First 1
function Await($op, [Type]$type) {
    $task = $asTask.MakeGenericMethod($type).Invoke($null, @($op))
    $null = $task.Wait(-1)
    $task.Result
}

$engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages()
foreach ($path in $args) {
    $lines = New-Object System.Collections.ArrayList
    try {
        $file = Await ([Windows.Storage.StorageFile]::GetFileFromPathAsync((Resolve-Path -LiteralPath $path).Path)) ([Windows.Storage.StorageFile])
        $stream = Await ($file.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
        $decoder = Await ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
        $bitmap = Await ($decoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
        $W = [double]$bitmap.PixelWidth; $H = [double]$bitmap.PixelHeight
        $result = Await ($engine.RecognizeAsync($bitmap)) ([Windows.Media.Ocr.OcrResult])
        foreach ($line in $result.Lines) {
            # A line's box is the union of its words' boxes.
            $x0 = 1e9; $y0 = 1e9; $x1 = 0; $y1 = 0
            foreach ($word in $line.Words) {
                $r = $word.BoundingRect
                $x0 = [Math]::Min($x0, $r.X); $y0 = [Math]::Min($y0, $r.Y)
                $x1 = [Math]::Max($x1, $r.X + $r.Width); $y1 = [Math]::Max($y1, $r.Y + $r.Height)
            }
            $null = $lines.Add([ordered]@{ text = $line.Text; x = $x0 / $W; y = $y0 / $H; w = ($x1 - $x0) / $W; h = ($y1 - $y0) / $H })
        }
        $stream.Dispose()
    } catch { }   # an unreadable image is just an image with no text, like on the Mac
    ConvertTo-Json -Compress -Depth 4 ([ordered]@{ file = $path; lines = @($lines) })
}
