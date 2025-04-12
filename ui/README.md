pip install PyQt6 pyinstaller

pyinstaller --onefile --windowed --noconsole --add-data "stylesheet.qss:." --name ESP32_UART_Tool qtui.py --clean --strip 
