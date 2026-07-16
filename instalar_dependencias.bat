@echo off
REM Instala tudo que o bot precisa para rodar. So precisa rodar isso UMA VEZ
REM (ou de novo se der erro de "modulo nao encontrado" ao rodar o bot).
cd /d "%~dp0"
python -m pip install -r requirements.txt
echo.
echo Pronto. Agora coloque o balancete (PDF) na pasta "entrada" e de
echo duplo-clique em rodar_bot.bat.
pause
