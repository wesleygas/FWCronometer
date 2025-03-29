import sys
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QPushButton, QLabel, QComboBox, QStackedWidget, QHBoxLayout
)
from PyQt6.QtSerialPort import QSerialPort, QSerialPortInfo
from PyQt6.QtCore import QIODevice, QTimer
from PyQt6.QtGui import QFont

import struct

END_PACKET_DELIMITER = b'akb'
RESET_PROBE_COMMAND = b'R'
REQUEST_PROBE_UPDATE = b'U'
CONFIGURE_AVERAGE_MODE = b'CA'
REQUEST_AVERAGE_UPDATE = b'A'

class BarrierProbe():
    def __init__(self, id):
        self.id = id
        self.pulse_time = 0

class StopwatchUI(QWidget):
    def __init__(self):
        super().__init__()
        self.probes = {i: BarrierProbe(i) for i in range(2)}  # Support for multiple probes
        self.selected_probe_a = 1
        self.selected_probe_b = 2
        self.init_ui()
        self.init_serial()
        self.init_timer()
        self.serial_buffer = b''
        
    def init_ui(self):
        self.setWindowTitle("Precision Stopwatch")
        self.setGeometry(200, 200, 400, 300)
        layout = QVBoxLayout()
        
        # Port Selection
        self.port_dropdown = QComboBox()
        self.refresh_ports()
        self.connect_button = QPushButton("Connect")
        self.connect_button.clicked.connect(self.connect_serial)
        
        port_layout = QHBoxLayout()
        port_layout.addWidget(QLabel("Select Port:"))
        port_layout.addWidget(self.port_dropdown)
        port_layout.addWidget(self.connect_button)
        layout.addLayout(port_layout)
        
        # Mode Selection
        self.mode_selector = QComboBox()
        self.mode_selector.addItems(["Instantaneous Mode", "Average Mode"])
        self.mode_selector.currentIndexChanged.connect(self.switch_mode)
        layout.addWidget(self.mode_selector)
        
        # Page Container
        self.pages = QStackedWidget()
        self.instantaneous_page = self.create_instantaneous_page()
        self.average_page = self.create_average_page()
        self.pages.addWidget(self.instantaneous_page)
        self.pages.addWidget(self.average_page)
        layout.addWidget(self.pages)
        
        self.setLayout(layout)
    
    def create_instantaneous_page(self):
        page = QWidget()
        layout = QVBoxLayout()
        
        self.time_displays = {}
        self.reset_buttons = {}
        
        for probe_id in self.probes:
            label = QLabel(f"Probe {probe_id}: 00:00.000")
            label.setFont(QFont("Courier", 20))
            self.time_displays[probe_id] = label
            layout.addWidget(label)
            
            button = QPushButton(f"Reset Probe {probe_id}")
            button.clicked.connect(lambda _, pid=probe_id: self.send_command(RESET_PROBE_COMMAND + bytes([pid])))
            self.reset_buttons[probe_id] = button
            layout.addWidget(button)
        
        page.setLayout(layout)
        return page
    
    def create_average_page(self):
        page = QWidget()
        layout = QVBoxLayout()
        
        self.probe_a_selector = QComboBox()
        self.probe_a_selector.addItems([str(p.id) for p in self.probes.values()])
        self.probe_a_selector.setCurrentIndex(0)
        self.probe_a_selector.currentIndexChanged.connect(self.update_probe_selection)
        layout.addWidget(QLabel("Select Probe A"))
        layout.addWidget(self.probe_a_selector)
        
        self.probe_b_selector = QComboBox()
        self.probe_b_selector.addItems([str(p.id) for p in self.probes.values()])
        self.probe_b_selector.setCurrentIndex(1)
        self.probe_b_selector.currentIndexChanged.connect(self.update_probe_selection)
        layout.addWidget(QLabel("Select Probe B"))
        layout.addWidget(self.probe_b_selector)
        
        self.average_display = QLabel("00:00.000")
        self.average_display.setFont(QFont("Courier", 30))
        layout.addWidget(self.average_display)

        button = QPushButton(f"Reset Probes")
        button.clicked.connect(self.reset_average_selected_probes)
        layout.addWidget(button)
        
        page.setLayout(layout)
        return page
    
    def switch_mode(self, index):
        self.pages.setCurrentIndex(index)
        if index == 1:
            self.configure_average_mode()

    def reset_average_selected_probes(self):
        self.send_command(RESET_PROBE_COMMAND + bytes([int(self.probe_a_selector.currentText())]))
        self.send_command(RESET_PROBE_COMMAND + bytes([int(self.probe_b_selector.currentText())]))
    
    def update_probe_selection(self):
        self.selected_probe_a = int(self.probe_a_selector.currentText())
        self.selected_probe_b = int(self.probe_b_selector.currentText())
        self.configure_average_mode()
    
    def configure_average_mode(self):
        self.send_command(CONFIGURE_AVERAGE_MODE + bytes([self.selected_probe_a, self.selected_probe_b]))
    
    def init_serial(self):
        self.serial = QSerialPort()
        self.serial.setBaudRate(115200)
        self.serial.readyRead.connect(self.read_serial_data)
    
    def connect_serial(self):
        if self.serial.isOpen():
            self.serial.close()
        
        selected_port = self.port_dropdown.currentText()
        if selected_port:
            self.serial.setPortName(selected_port)
            if self.serial.open(QIODevice.OpenModeFlag.ReadWrite):
                print(f"Connected to {selected_port}")
            else:
                print("Failed to open serial port.")
    
    def refresh_ports(self):
        self.port_dropdown.clear()
        ports = QSerialPortInfo.availablePorts()
        for port in ports:
            self.port_dropdown.addItem(port.portName())
    
    def send_command(self, command: bytes):
        if self.serial.isOpen():
            self.serial.write(command + END_PACKET_DELIMITER)
    
    def read_serial_data(self):
        self.serial_buffer += self.serial.readAll().data()
        while END_PACKET_DELIMITER in self.serial_buffer:
            pkt, self.serial_buffer = self.serial_buffer.split(END_PACKET_DELIMITER, 1)
            print(pkt)
            if pkt.startswith(REQUEST_AVERAGE_UPDATE):
                average_time = struct.unpack('<L', pkt[1:])[0]
                self.update_average_display(average_time)
            elif pkt.startswith(REQUEST_PROBE_UPDATE):
                probe_id, pulse_time = struct.unpack('<BL', pkt[1:])
                self.update_instantaneous_display(probe_id, pulse_time)
    
    def update_average_display(self, average_time):
        self.average_display.setText(f"{average_time*1e-6:,.4f}")
    
    def update_instantaneous_display(self, probe_id, pulse_time):
        if probe_id in self.time_displays:
            self.time_displays[probe_id].setText(f"Probe {probe_id}: {pulse_time*1e-6:,.4f}")
    
    def init_timer(self):
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.poll_current_mode)
        self.timer.start(200)
    
    def poll_current_mode(self):
        if self.pages.currentIndex() == 0:
            for probe_id in self.probes:
                self.send_command(REQUEST_PROBE_UPDATE + bytes([probe_id]))
        elif self.pages.currentIndex() == 1:
            self.send_command(REQUEST_AVERAGE_UPDATE)
    
if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = StopwatchUI()
    window.show()
    sys.exit(app.exec())
