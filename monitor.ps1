param(
    [int]$ProcId,
    [string]$OutputDir,
    [datetime]$StartTime,
    [string]$ErrFile,
    [string]$OutFile,
    [switch]$Quiet
)

Add-Type -AssemblyName System.Windows.Forms

# 예약 실행(-Quiet)에서는 클릭할 사람이 없으므로 팝업 대신 로그 한 줄만 남긴다.
$logDir = Join-Path (Split-Path $OutputDir -Parent) 'logs'
function Notify([string]$title, [string]$body, [string]$icon) {
    if ($Quiet) {
        "$(Get-Date -Format o)  [$title] $($body -replace "`r?`n", ' / ')" |
            Out-File -FilePath (Join-Path $logDir 'scheduled.log') -Encoding UTF8 -Append
    } else {
        [System.Windows.Forms.MessageBox]::Show($body, $title,
            [System.Windows.Forms.MessageBoxButtons]::OK,
            [System.Windows.Forms.MessageBoxIcon]$icon) | Out-Null
    }
}

Wait-Process -Id $ProcId -ErrorAction SilentlyContinue

# 에이전트가 모호한 주제를 알아서 구체화해 폴더명을 바꿀 수 있어 -> 입력한 주제로 경로를 예측하지 않고,
# 시작 시각 이후 새로 생긴 final.html 중 가장 최근 것을 찾는다.
$final = Get-ChildItem -Path $OutputDir -Filter 'final.html' -Recurse -ErrorAction SilentlyContinue |
    Where-Object { $_.LastWriteTime -ge $StartTime } |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1

if ($final) {
    Notify '블로그 자동화 - 완료' "블로그 글 작성이 완료되었습니다.`n`n$($final.FullName)" 'Information'
} else {
    # claude.exe는 실패 사유(세션 한도 등)를 stderr가 아니라 stdout에 쓰는 경우가 있어 ->
    # 항상 비어있을 수 있는 ErrFile 경로만 보여주지 말고, 실제 로그 내용을 같이 띄운다.
    $tail = @($ErrFile, $OutFile) | Where-Object { $_ -and (Test-Path $_) } |
        ForEach-Object { Get-Content -Path $_ -Tail 5 -Encoding UTF8 -ErrorAction SilentlyContinue } |
        Where-Object { $_ -and $_.Trim() -ne '' }
    $detail = if ($tail) { ($tail -join "`n") } else { '(로그 내용 없음)' }

    Notify '블로그 자동화 - 확인 필요' "파이프라인이 종료됐지만 최종 파일을 찾지 못했습니다.`n`n$detail`n`n로그 파일:`n$OutFile`n$ErrFile" 'Warning'
}
