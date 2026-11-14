param(
    [string]$Topic,
    [switch]$Today   # 스케줄러용: 주제를 "오늘 주제"로 고정 (CLAUDE.md가 요일별 주제 자동 적용).
)

Add-Type -AssemblyName Microsoft.VisualBasic
Add-Type -AssemblyName System.Windows.Forms

# -Today 또는 -Topic 이 있으면 비대화형(스케줄러) 모드: 주제 입력창·팝업 없이 바로 실행.
# 요일 계산을 모델에 맡기면 미래 날짜 요일을 틀리게 잡는다(2026-09-06 일요일을
# 토요일로 계산 -> "돌아오는 주말 전망"을 써버린 사례). Windows가 계산한 실제
# 요일명을 주제로 넘기고, 프롬프트에도 오늘 날짜·요일을 못박는다.
$dowKo = @{ Sunday='일요일'; Monday='월요일'; Tuesday='화요일'; Wednesday='수요일'; Thursday='목요일'; Friday='금요일'; Saturday='토요일' }
$todayKo = $dowKo[[string](Get-Date).DayOfWeek]
$todayDate = Get-Date -Format 'yyyy-MM-dd'
if ($Today) { $Topic = '오늘 주제' }
$interactive = [string]::IsNullOrWhiteSpace($Topic)

$blogDir = $PSScriptRoot
$logDir = Join-Path $blogDir 'logs'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

# --- 단일 인스턴스 락 --------------------------------------------------------
# run.ps1 은 claude 를 Start-Process 로 띄우고 바로 끝나므로, 중복 실행을 막지
# 않으면 무거운 파이프라인이 여러 개 병렬로 돌면서 세션 사용량(5시간 한도)을
# 순식간에 태운다(화요일 주제가 특히 무거움). 락 파일 = "PID`n시작시각(ISO)".
# 완료 시 monitor.ps1 이 지운다.
$lockFile = Join-Path $logDir 'pipeline.lock'
if (Test-Path $lockFile) {
    $lk = @(Get-Content $lockFile -ErrorAction SilentlyContinue)
    $lockPid = $lk[0] -as [int]
    $lockAgeMin = if ($lk[1]) { ((Get-Date) - [datetime]$lk[1]).TotalMinutes } else { 0 }
    $proc0 = if ($lockPid) { Get-Process -Id $lockPid -ErrorAction SilentlyContinue } else { $null }
    # 살아있는 PID 가 -p 파이프라인 실행이 맞고, bg 대기 상한(30분)+여유를 넘겼으면
    # 진짜 멈춘 것으로 보고 정리 후 진행. 그 외에는 실행 중으로 보고 거부.
    $lockAge = [math]::Round($lockAgeMin)
    $isPipeline = $proc0 -and ((Get-CimInstance Win32_Process -Filter "ProcessId=$lockPid" -ErrorAction SilentlyContinue).CommandLine -match '\s-p\s')
    if ($proc0 -and -not ($isPipeline -and $lockAgeMin -gt 40)) {
        $msg = "이미 파이프라인이 실행 중입니다 (PID $lockPid, $lockAge 분 경과).`n중복 실행은 세션 사용량을 빠르게 소진하므로 취소합니다.`n`n끝난 뒤 다시 실행하거나, 멈춘 게 확실하면 logs\pipeline.lock 파일을 지우세요."
        if ($interactive) {
            [System.Windows.Forms.MessageBox]::Show($msg, '블로그 자동화 - 중복 실행',
                [System.Windows.Forms.MessageBoxButtons]::OK,
                [System.Windows.Forms.MessageBoxIcon]::Warning) | Out-Null
        } else {
            "$(Get-Date -Format o)  중복 실행 취소: PID $lockPid 실행 중 ($lockAge 분)" |
                Out-File -FilePath (Join-Path $logDir 'scheduled.log') -Encoding UTF8 -Append
        }
        exit
    }
    if ($isPipeline -and $lockAgeMin -gt 40) {
        Stop-Process -Id $lockPid -Force -ErrorAction SilentlyContinue   # 멈춘 파이프라인 정리
        "$(Get-Date -Format o)  멈춘 파이프라인 정리: PID $lockPid ($lockAge 분)" |
            Out-File -FilePath (Join-Path $logDir 'scheduled.log') -Encoding UTF8 -Append
    }
    Remove-Item $lockFile -ErrorAction SilentlyContinue   # 죽었거나 정리한 락 -> 스테일, 제거
}

if ($interactive) {
    $topic = [Microsoft.VisualBasic.Interaction]::InputBox('블로그 글 주제를 입력하세요', '블로그 자동화', '')
    if ([string]::IsNullOrWhiteSpace($topic)) {
        exit
    }
} else {
    $topic = $Topic
}

$topic = $topic -replace '"', ''

# 요일별 주제 표를 강제하는 줄은 -Today(스케줄러) 실행에서만 넣는다.
# 사용자가 -Topic 으로 오늘이 아닌 요일("화요일 주제" 등)을 명시하면
# 이 줄이 "오늘 요일 행을 쓰라"고 충돌시켜 에이전트가 되묻고 멈춘다.
# 요일명만 넘겼을 때의 주제 치환은 CLAUDE.md 주제 해석 규칙이 이미 처리한다.
$dayRow = if ($Today) { "`n- CLAUDE.md `"오늘 주제`" 규칙대로 0단계(agents/topic-pick.md, 국내 커뮤니티 핫이슈 선정)를 먼저 서브 에이전트에 위임하고(위임 프롬프트에 'mcp__claude-in-chrome 도구로 실제 Chrome에서 읽고, 연결 실패 시 20초 간격 2회 재시도, 직접 작업·파일 생성 후 종료'를 명시), 그 결과 주제로 1~5단계를 진행하라. 실패(FALLBACK) 시에만 요일별 주제 표의 `"$todayKo`" 행을 사용하라." } else { '' }

$prompt = @"
$topic 주제로 블로그 자동화 파이프라인을 CLAUDE.md 지침대로 처음부터 끝까지 실행해줘.

[오늘 날짜 - 이 값을 그대로 신뢰하고 요일을 다시 계산하지 말 것]
- 오늘은 $todayDate, $todayKo 이다.$dayRow
- "가장 최근 토요일", "가장 최근 일요일", "돌아오는 주말", "지난 주말" 같은 표현은 전부 이 오늘 날짜($todayDate, $todayKo)를 기준으로 해석하라. 예: 오늘이 일요일이면 "가장 최근 토요일"은 바로 어제다.

[비대화형 실행 규칙 - 반드시 지킬 것]
- 이 실행은 비대화형이라 되물어도 답할 사람이 없다. 주제가 모호하거나 정보가 부족해도 절대 되묻지 말고 네가 알아서 구체화해서 바로 진행해.
- 4단계(1.리서치 -> 2.글쓰기 -> 3.이미지 생성 -> 4.최종 조립)를 한 번의 실행 안에서 연속으로 전부 끝내라. 한 단계가 끝나면 사용자 확인을 기다리지 말고 즉시 다음 단계로 넘어가라.
- 서브 에이전트를 호출한 뒤에는 그 결과가 돌아올 때까지 네가 직접 기다렸다가, 결과를 받으면 곧바로 다음 단계 서브 에이전트를 호출하라. 결과를 기다리겠다는 식으로 말하고 턴을 끝내면 안 된다. 파이프라인이 중간에 멈춘다.
- 어떤 작업(서브 에이전트, 검색, 셸 명령)도 백그라운드로 돌리지 마라. 전부 포그라운드로 실행해서 그 자리에서 결과를 받은 뒤 다음으로 넘어가라. "백그라운드로 계속 진행 중", "완료 대기 중" 같은 상태로 턴을 끝내면 실행이 통째로 종료돼 최종 파일이 안 만들어진다.
- 서브 에이전트 결과가 미흡하면(파일 미생성, 내용 부족 등) 같은 단계를 한 번 더 재시도한 뒤 진행하라.
- 종료 조건: output/[주제]/final.html 파일이 실제로 생성되어야만 작업이 끝난 것이다. 그 전에는 어떤 이유로도 실행을 마치지 마라.
- 마지막에 생성된 final.html의 전체 경로를 한 줄로 출력하고 끝내라.
"@

$stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$outFile = Join-Path $logDir "pipeline_${stamp}.log"
$errFile = Join-Path $logDir "pipeline_${stamp}.err.log"

$startTime = Get-Date

# secrets.env (repo 루트, .gitignore 처리됨) 의 KEY=value 줄을 환경변수로 올린다.
# 예약(-p) 실행에서 claude 하위 프로세스·서브에이전트·파이썬 스크립트가
# GEMINI_API_KEY 등을 상속받게 하려면 여기서 넣어줘야 한다.
$secretsFile = Join-Path $blogDir 'secrets.env'
if (Test-Path $secretsFile) {
    Get-Content $secretsFile -Encoding UTF8 | ForEach-Object {
        $line = $_.Trim()
        if ($line -and -not $line.StartsWith('#') -and $line.Contains('=')) {
            $k, $v = $line.Split('=', 2)
            Set-Item -Path "Env:$($k.Trim())" -Value $v.Trim()
        }
    }
}

# 비대화형(-p) 실행에서 턴이 끝난 시점에 백그라운드 작업이 남아 있으면 claude가 기본 600초 뒤
# 그 작업들을 강제 종료하고 나가버린다(최종 파일 미생성). 기본 10분 -> 30분으로 여유를 준다
# (완전 무한 대기(0)는 진짜 멈춘 작업일 때 완료 팝업도 영영 안 떠서 배제).
$env:CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS = '1800000'

# 예약 실행(-Today)이면 Chrome을 먼저 띄워 Claude in Chrome 확장이 연결되게 한다
# (topic-pick가 에펨코리아를 실제 Chrome으로 읽어야 함). 이미 떠 있으면 건너뜀.
if ($Today) {
    if (-not (Get-Process chrome -ErrorAction SilentlyContinue)) {
        $chromeExe = @("$env:ProgramFiles\Google\Chrome\Application\chrome.exe",
                       "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe",
                       "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe") | Where-Object { Test-Path $_ } | Select-Object -First 1
        if ($chromeExe) { Start-Process $chromeExe -ArgumentList 'about:blank' }
    }
    # 확장 서비스워커·네이티브 호스트 연결 대기. PC 05:30 부팅 -> 05:34 catch-up 실행이라 부팅 직후엔 45초로 부족(11/9~15 연결 실패).
    Start-Sleep -Seconds 30
    # 연결될 때까지 프로브 폴링(최대 6회 ≈ 5분). 성공하면 즉시 진행, 끝까지 실패해도 파이프라인은 진행(topic-pick가 재시도/FALLBACK).
    for ($i = 0; $i -lt 6; $i++) {
        $job = Start-Job { Set-Location $using:blogDir; claude --chrome -p "ToolSearch로 'select:mcp__claude-in-chrome__tabs_context_mcp'를 시도. 도구가 나오면 호출해 OK 한 줄, 아니면 NOTOOL 한 줄만 출력." }
        if (Wait-Job $job -Timeout 90) { $out = Receive-Job $job | Out-String } else { $out = '' ; Stop-Job $job }
        Remove-Job $job -Force
        if ($out -match 'OK' -and $out -notmatch 'NOTOOL') { break }
        Start-Sleep -Seconds 30
    }
}

try {
    # claude.exe를 직접 실행 + Start-Process 자체 리다이렉션 사용 (중첩 셸/버퍼링으로 로그가 통째로 사라지는 문제 방지).
    # stdin은 굳이 연결하지 않음 -> 빈 파일로 연결하면 즉시 EOF가 되어 파이프라인이 시작도 못 하고 죽는 현상이 있었음.
    # -ArgumentList를 배열로 주면 Windows PowerShell 5.1이 공백 포함 문자열을 자동으로 안 묶어주고 그냥 쪼개버림 -> 프롬프트를 직접 따옴표로 감싼 단일 문자열로 전달.
    $proc = Start-Process -FilePath 'claude' `
        -ArgumentList "--chrome --dangerously-skip-permissions -p `"$prompt`"" `
        -WorkingDirectory $blogDir `
        -WindowStyle Hidden `
        -RedirectStandardOutput $outFile `
        -RedirectStandardError $errFile `
        -PassThru

    Set-Content -Path $lockFile -Value "$($proc.Id)`n$($startTime.ToString('o'))" -Encoding ascii   # monitor.ps1 이 완료 시 삭제

    if ($interactive) {
        [System.Windows.Forms.MessageBox]::Show(
            '에이전트 수행 시작합니다.',
            '블로그 자동화',
            [System.Windows.Forms.MessageBoxButtons]::OK,
            [System.Windows.Forms.MessageBoxIcon]::Information
        ) | Out-Null
    }

    # 완료 감시는 별도 프로세스로 분리 -> 이 스크립트(및 InputBox 창)가 끝나도 계속 살아서 완료 팝업을 띄운다.
    # 에이전트가 모호한 주제를 알아서 구체화해 폴더명이 입력값과 달라질 수 있으므로,
    # 경로를 미리 예측하지 않고 output 전체에서 시작 시각 이후 생긴 final.html을 찾도록 넘긴다.
    $outputDir = Join-Path $blogDir 'output'
    $monitorScript = Join-Path $blogDir 'monitor.ps1'
    $monitorArgs = "-NoProfile -WindowStyle Hidden -File `"$monitorScript`" -ProcId $($proc.Id) -OutputDir `"$outputDir`" -StartTime `"$($startTime.ToString('o'))`" -ErrFile `"$errFile`" -OutFile `"$outFile`" -LockFile `"$lockFile`""
    if (-not $interactive) { $monitorArgs += " -Quiet" }
    Start-Process -FilePath 'powershell' -ArgumentList $monitorArgs -WindowStyle Hidden
} catch {
    if ($interactive) {
        [System.Windows.Forms.MessageBox]::Show(
            "실행 실패:`n$($_.Exception.Message)",
            '블로그 자동화 - 오류',
            [System.Windows.Forms.MessageBoxButtons]::OK,
            [System.Windows.Forms.MessageBoxIcon]::Error
        ) | Out-Null
    } else {
        "$(Get-Date -Format o)  실행 실패: $($_.Exception.Message)" |
            Out-File -FilePath (Join-Path $logDir "launch-error_${stamp}.log") -Encoding UTF8
    }
}
