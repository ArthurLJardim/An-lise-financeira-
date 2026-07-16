@echo off
REM Duplo-clique aqui para rodar o bot: ele analisa todo PDF de balancete
REM que estiver na pasta "entrada" e abre o relatorio no Bloco de Notas.
REM Antes da primeira vez, rode instalar_dependencias.bat uma vez.
cd /d "%~dp0"
python rodar_bot.py
pause
