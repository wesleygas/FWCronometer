from machine import Pin, UART
from sensing import TimedSensor, DualPoint
import micropython as mp
import ustruct as us
import sys
import uselect
import time

# --- Configuration ---
# Set to True to use REPL USB CDC for communication
# Set to False to use UART0 (Pins 0, 1) with a separate adapter
USE_REPL_COMM = True
# -------------------

led = Pin(25, Pin.OUT)  # Pico's built-in LED

# --- Sensor Setup ---
probes = [TimedSensor(2), TimedSensor(3), TimedSensor(4), TimedSensor(5)]
dps = [DualPoint() for _ in range(len(probes)//2)]

# --- Communication Setup ---
END_PACKET_DELIMITER = b"akb"
comm_buffer = b""
cmd = b''

if USE_REPL_COMM:
    # Use standard input/output (REPL)
    comm_input = sys.stdin.buffer # Use buffer for binary data
    comm_output = sys.stdout.buffer # Use buffer for binary data
    # Setup polling for non-blocking reads from stdin
    poll = uselect.poll()
    poll.register(sys.stdin, uselect.POLLIN)
    print("Communication configured for REPL (USB CDC)")
else:
    # Use dedicated UART0
    uart = UART(0, 115200, tx=Pin(0), rx=Pin(1))
    comm_input = uart
    comm_output = uart
    poll = None # Not needed for uart.any()
    print("Communication configured for UART0 (Pins 0, 1)")

def comm_any():
    """Checks if there is data available to read."""
    if USE_REPL_COMM:
        # Check poll results with a zero timeout (non-blocking)
        return bool(poll.poll(0))
    else:
        # Use UART's built-in method
        return comm_input.any()

def comm_read(nbytes=None):
    """Reads data from the communication channel."""
    return comm_input.read(1)

def send_comm(data):
    """Sends data over the communication channel."""
    comm_output.write(data + END_PACKET_DELIMITER)

def send_comm_str(data):
    """Sends a string over the communication channel."""
    #print(data)
    comm_output.write(b'LOG_'+ data.encode() + END_PACKET_DELIMITER)
    pass

def process_command(cmd):
#     print(cmd) # DEBUG: Be careful printing when using REPL comms!
    try:
        if not cmd: # Ignore empty commands
            return
        if(cmd[0] == ord('r')):  # Reset average mode
            id = us.unpack('<B', cmd[1:])[0]
            dps[id].reset()
            send_comm(b'OK')
        elif(cmd[0] == ord('A')):
            id = us.unpack('<B', cmd[1:])[0]
            tout = b'A' + us.pack('<BL', id, dps[id].get_trip_time())
            send_comm(tout)
        elif(cmd[0] == ord('R')):
            probe_id = us.unpack('<B', cmd[1:])[0]
            probes[probe_id].reset()
            # print(f"Reset PID {probe_id}") # DEBUG: Avoid print
        elif(cmd[0] == ord('U')):
    #         print("probe update request") # DEBUG: Avoid print
            probe_id = us.unpack('<B', cmd[1:])[0]
            ptime = probes[probe_id].get_pulse_time()
            tout = b'U' + us.pack('<BL', probe_id, ptime)
    #         print(f"Sending time: {ptime} for probe {probe_id} | Started {probes[probe_id].last_set} -> ended {probes[probe_id].last_release}") # DEBUG: Avoid print
            send_comm(tout)
        elif(cmd[0] == ord('C')):
            # Config mode
            if(cmd[1] == ord('A')):
                # Config absolute mode
                id, A_probe, B_probe = us.unpack('<BBB', cmd[2:])
                dps[id].set_probes(probes[A_probe], probes[B_probe])
                # print(f"Configuring probe {A_probe} as A and {B_probe} as B") # DEBUG: Avoid print
                send_comm(b'OK')
            elif(cmd[1] == ord('I')):  # Restore average probes
                id = us.unpack('<B', cmd[2:])
                dps[id].restore_probes()
                send_comm(b'OK')
        elif(cmd[:3] == b'KBD'):
            mp.kbd_intr(3)
            print("Restoring CTRL+C")
            raise KeyboardInterrupt
        else:
            send_comm_str("unknown command: " + str(cmd)) # DEBUG: Avoid print
            pass # Silently ignore unknown commands or send an error code
            # send_comm(b'ERR_UNKNOWN_CMD')
    except Exception as e:
        # print(f"Error processing command {cmd}: {e}") # DEBUG: Avoid print
        # Consider sending an error message back to the UI
        send_comm_str('ERR_' + f"Error processing command {cmd}: {e}")
        pass # Or silently ignore errors for now

def handle_comm():
    """Handles incoming communication data."""
    global comm_buffer, cmd
    # Check if data is available using the appropriate method
    if comm_any():
        led.toggle()
        # Read available data. Read all available if using REPL to avoid potential blocking
        data = comm_read()
        #print("Got data", data)
        if data:
            comm_buffer += data
            # Process buffer for complete packets
            while END_PACKET_DELIMITER in comm_buffer:
                cmd, comm_buffer = comm_buffer.split(END_PACKET_DELIMITER, 1)
                process_command(cmd)

def main():
    print("Starting...", end="")
    time.sleep(1) # Give time for the program to be interrupted before starting main
    ## 
    #  This is not enough time to stop execution when the board is freshly
    #  plugged in. This is why there is a special Command "KBD" that restores keyboard
    #  interrupt. You can use it anywhere by sending "akbKBDakb"
    ##
    mp.kbd_intr(-1)  # Disable the hability to introduce keyboard interrupts by receiving ascii EXT (0x03) byte
    print("Ready")
    try:
        while True:
            handle_comm()
            # It's often good practice to have a small sleep in the main loop
            # to prevent pegging the CPU if there's nothing to do,
            # especially if sensor reading isn't happening here.
            time.sleep_ms(1) # Optional: Adjust as needed
    except:
        pass
    mp.kbd_intr(3)

# Assuming sensing.py handles interrupts or polling for the sensors internally
main()

