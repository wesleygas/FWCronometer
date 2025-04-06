from machine import Pin
import time

class TimedSensor():
    def __init__(self, pin_number, active_low=False, auto_reseting=False, trigger_callback=lambda *args, **kwargs: None):
        self.pin = Pin(pin_number, Pin.IN)
        self.now = time.ticks_us()
        self.last_set = self.now
        self.last_release = self.now
        self.active_low = active_low
        self.auto_reseting = auto_reseting
#         self.last_handled_pin = self.pin
        self.pin.irq(
            handler=self.resetting_handler if auto_reseting else self.non_resetting_handler,
            trigger=Pin.IRQ_FALLING|Pin.IRQ_RISING
        )
        self.set_trigger = False
        self.release_trigger = False
        self.trigger_callback = trigger_callback
        self.owner = None
    
    def resetting_handler(self, pin):
        self.now = time.ticks_us()
        if(self.is_active() and not self.set_trigger):
#             print(f"Active | Prb {self.pin} -> Hnd {pin}")
            self.last_set = self.now
            self.set_trigger = True
            self.trigger_callback()
        else:
#             print(f"Active | Prb {self.pin} -> Hnd {pin}")
            self.last_release = self.now
            self.release_trigger = True
    
    def non_resetting_handler(self, pin):
        if(self.release_trigger):
            return
        self.now = time.ticks_us()
        active = self.is_active()
        if(active and not self.set_trigger):
            print(f"Active {self.is_active()} | Prb {self.pin} -> Hnd {pin}")
            self.last_set = self.now
            self.set_trigger = True
            self.trigger_callback()
        elif(not active):
            print(f"Inactive {self.is_active()} | Prb {self.pin} -> Hnd {pin}")
            self.last_release = self.now
            self.release_trigger = True

    def get_pulse_time(self):
        return time.ticks_diff(time.ticks_us() if self.is_active() and not self.release_trigger else self.last_release, self.last_set)
    
    def is_active(self):
        return self.pin.value()^self.active_low
    
    def reset(self):
        # Dont allow the set trigger to be reset if the sensor is currently activated
        if(not self.is_active()):
            self.set_trigger = False
        self.release_trigger = False
        self.last_release = self.last_set
    
    def disable(self):
        self.pin.irq(handler=None)


class SinglePoint():
    def __init__(self):
        pass


class DualPoint():
    def __init__(self):
        self.pA: TimedSensor = None
        self.pB: TimedSensor = None
    
    def reset(self, block=False):
        if self.pA is None:
            return
        while(self.pA.is_active() or self.pB.is_active()):
            time.sleep(0.5)
        self.pA.reset()
        self.pB.reset()
    
    def start_triggered(self):
        return self.pA.set_trigger
    
    def stop_triggered(self):
        return self.pA.set_trigger and self.pB.set_trigger

    def get_trip_time(self):
        if self.pA is None or not self.pA.set_trigger:
            return 0
        end = self.pB.last_set if self.stop_triggered() else time.ticks_us()
        return time.ticks_diff(end, self.pA.last_set)
    
    def set_probes(self, pA: TimedSensor, pB: TimedSensor):
        if(isinstance(pA.owner, DualPoint) and pA.owner != self):
            print("Changing owner")
            pA.owner.restore_probes()
        pA.owner = self
        self.pA = pA
        self.pA.trigger_callback = self.clear_b_probe
        if(isinstance(pB.owner, DualPoint) and pB.owner != self):
            print("Changing owner")
            pB.owner.restore_probes()
        pB.owner = self
        self.pB = pB
        self.reset()
    
    def clear_b_probe(self):
        self.pB.reset()

    def restore_probes(self):
        if self.pA is not None:
            self.pA.reset()
            self.pA.trigger_callback = lambda *args, **kwargs: None
            self.pA.owner = None
            self.pA = None
        if self.pB is not None:
            self.pB.reset()
            self.pB.owner = None
            self.pB = None

