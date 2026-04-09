@echo off
title MARK-45 — Instalador
echo.
echo  ======================================================
echo   M A R K  4 5  — Hive Kernel — Instalador
echo   Creado por Ali (Sidi3Ali)
echo  ======================================================
echo.

REM Verificar Python
python --version 2>NUL
if errorlevel 1 (
    echo [ERROR] Python no encontrado. Instala Python 3.10+ desde python.org
    pause
    exit /b 1
)

echo [1/4] Actualizando pip...
python -m pip install --upgrade pip

echo.
echo [2/4] Instalando dependencias principales...
pip install openai requests rapidfuzz edge-tts pygame SpeechRecognition psutil pynvml pyautogui mss Pillow pyttsx3 rapidfuzz

echo.
echo [3/4] Instalando dependencias de audio (pyaudio)...
pip install pyaudio
if errorlevel 1 (
    echo [AVISO] pyaudio no se pudo instalar automaticamente.
    echo         Descarga el wheel desde https://www.lfd.uci.edu/~gohlke/pythonlibs/#pyaudio
    echo         e instala con: pip install PyAudio-X.X.X-cpXX-cpXX-win_amd64.whl
)

echo.
echo [4/4] Instalando dependencias opcionales...
pip install spotipy pycaw comtypes keyboard
if errorlevel 1 (
    echo [AVISO] Algunas dependencias opcionales no se instalaron. No es critico.
)

echo.
echo  ======================================================
echo   Instalacion completada.
echo   Ejecuta:  python main.py
echo   o debug:  python main.py --debug
echo   o CLI:    python main.py --cli
echo.
echo   NOTA: Asegurate de tener LM Studio o Ollama activo
echo         con un modelo cargado antes de lanzar MARK 45.
echo  ======================================================
echo.
pause
