@echo off
setlocal EnableExtensions

set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..") do set "REPO_ROOT=%%~fI"

set "UV_CACHE_DIR=%REPO_ROOT%\.uv-cache"
if not defined COREPACK_HOME set "COREPACK_HOME=%REPO_ROOT%\.corepack"
set "TEMP=%REPO_ROOT%\.tmp"
set "TMP=%REPO_ROOT%\.tmp"
set "PATH=Y:\Software\just;Y:\Software\nodes\nodejs;%PATH%"

if not exist "%UV_CACHE_DIR%" mkdir "%UV_CACHE_DIR%"
if not exist "%COREPACK_HOME%" mkdir "%COREPACK_HOME%"
if not exist "%TEMP%" mkdir "%TEMP%"

if "%~1"=="--" shift

if "%~1"=="" (
    echo RepoRoot=%REPO_ROOT%
    echo UV_CACHE_DIR=%UV_CACHE_DIR%
    echo COREPACK_HOME=%COREPACK_HOME%
    echo TEMP=%TEMP%
    where just 2>nul
    where corepack 2>nul
    where node 2>nul
    exit /b 0
)

set "PROGRAM=%~1"
shift
set "PROGRAM_ARGS="

:collect_args
if "%~1"=="" goto run_command
set "PROGRAM_ARGS=%PROGRAM_ARGS% "%~1""
shift
goto collect_args

:run_command
if /I "%PROGRAM%"=="pnpm" (
    corepack pnpm %PROGRAM_ARGS%
) else (
    %PROGRAM% %PROGRAM_ARGS%
)
exit /b %ERRORLEVEL%
