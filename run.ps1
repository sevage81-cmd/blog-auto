Add-Type -AssemblyName Microsoft.VisualBasic
Add-Type -AssemblyName System.Windows.Forms

$topic = [Microsoft.VisualBasic.Interaction]::InputBox('블로그 글 주제를 입력하세요', '블로그 자동화', '')

if ([string]::IsNullOrWhiteSpace($topic)) {
    exit
}

$blogDir = $PSScriptRoot
$topic = $topic -replace '"', ''
$prompt = @"
$topic 주제로 블로그 자동화 파이프라인을 CLAUDE.md 지침대로 처음부터 끝까지 실행해줘.

[비대화형 실행 규칙 - 반드시 지킬 것]
- 이 실행은 비대화형이라 되물어도 답할 사람이 없다. 주제가 모호하거나 정보가 부족해도 절대 되묻지 말고 네가 알아서 구체화해서 바로 진행해.
- 4단계(1.리서치 -> 2.글쓰기 -> 3.이미지 생성 -> 4.최종 조립)를 한 번의 실행 안에서 연속으로 전부 끝내라. 한 단계가 끝나면 사용자 확인을 기다리지 말고 즉시 다음 단계로 넘어가라.
- 서브 에이전트를 호출한 뒤에는 그 결과가 돌아올 때까지 네가 직접 기다렸다가, 결과를 받으면 곧바로 다음 단계 서브 에이전트를 호출하라. 결과를 기다리겠다는 식으로 말하고 턴을 끝내면 안 된다. 파이프라인이 중간에 멈춘다.
- 어떤 작업(서브 에이전트, 검색, 셸 명령)도 백그라운드로 돌리지 마라. 전부 포그라운드로 실행해서 그 자리에서 결과를 받은 뒤 다음으로 넘어가라. "백그라운드로 계속 진행 중", "완료 대기 중" 같은 상태로 턴을 끝내면 실행이 통째로 종료돼 최종 파일이 안 만들어진다.
- 서브 에이전트 결과가 미흡하면(파일 미생성, 내용 부족 등) 같은 단계를 한 번 더 재시도한 뒤 진행하라.
- 종료 조건: output/[주제]/final.html 파일이 실제로 생성되어야만 작업이 끝난 것이다. 그 전에는 어떤 이유로도 실행을 마치지 마라.
- 마지막에 생성된 final.html의 전체 경로를 한 줄로 출력하고 끝내라.
"@

$logDir = Join-Path $blogDir 'logs'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$outFile = Join-Path $logDir "pipeline_${stamp}.log"
$errFile = Join-Path $logDir "pipeline_${stamp}.err.log"

$startTime = Get-Date

# 비대화형(-p) 실행에서 턴이 끝난 시점에 백그라운드 작업이 남아 있으면 claude가 기본 600초 뒤
# 그 작업들을 강제 종료하고 나가버린다(최종 파일 미생성). 기본 10분 -> 30분으로 여유를 준다
# (완전 무한 대기(0)는 진짜 멈춘 작업일 때 완료 팝업도 영영 안 떠서 배제).
$env:CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS = '1800000'

try {
    # claude.exe를 직접 실행 + Start-Process 자체 리다이렉션 사용 (중첩 셸/버퍼링으로 로그가 통째로 사라지는 문제 방지).
    # stdin은 굳이 연결하지 않음 -> 빈 파일로 연결하면 즉시 EOF가 되어 파이프라인이 시작도 못 하고 죽는 현상이 있었음.
    # -ArgumentList를 배열로 주면 Windows PowerShell 5.1이 공백 포함 문자열을 자동으로 안 묶어주고 그냥 쪼개버림 -> 프롬프트를 직접 따옴표로 감싼 단일 문자열로 전달.
    $proc = Start-Process -FilePath 'claude' `
        -ArgumentList "--dangerously-skip-permissions -p `"$prompt`"" `
        -WorkingDirectory $blogDir `
        -WindowStyle Hidden `
        -RedirectStandardOutput $outFile `
        -RedirectStandardError $errFile `
        -PassThru

    [System.Windows.Forms.MessageBox]::Show(
        '에이전트 수행 시작합니다.',
        '블로그 자동화',
        [System.Windows.Forms.MessageBoxButtons]::OK,
        [System.Windows.Forms.MessageBoxIcon]::Information
    ) | Out-Null

    # 완료 감시는 별도 프로세스로 분리 -> 이 스크립트(및 InputBox 창)가 끝나도 계속 살아서 완료 팝업을 띄운다.
    # 에이전트가 모호한 주제를 알아서 구체화해 폴더명이 입력값과 달라질 수 있으므로,
    # 경로를 미리 예측하지 않고 output 전체에서 시작 시각 이후 생긴 final.html을 찾도록 넘긴다.
    $outputDir = Join-Path $blogDir 'output'
    $monitorScript = Join-Path $blogDir 'monitor.ps1'
    Start-Process -FilePath 'powershell' `
        -ArgumentList "-NoProfile -WindowStyle Hidden -File `"$monitorScript`" -ProcId $($proc.Id) -OutputDir `"$outputDir`" -StartTime `"$($startTime.ToString('o'))`" -ErrFile `"$errFile`" -OutFile `"$outFile`"" `
        -WindowStyle Hidden
} catch {
    [System.Windows.Forms.MessageBox]::Show(
        "실행 실패:`n$($_.Exception.Message)",
        '블로그 자동화 - 오류',
        [System.Windows.Forms.MessageBoxButtons]::OK,
        [System.Windows.Forms.MessageBoxIcon]::Error
    ) | Out-Null
}
