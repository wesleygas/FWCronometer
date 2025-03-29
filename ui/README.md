pip install PyQt6 pyinstaller

pyinstaller --onefile --windowed --noconsole --name ESP32_UART_Tool ui/qtui.py --clean --strip 
