class SafetyState:
    def __init__(self, command_timeout: float):
        self.command_timeout = command_timeout
        self.emergency_stop = True
        self.last_command_time = None
        self.motion_command_active = False

    def accept_command(self, now: float) -> bool:
        if self.emergency_stop:
            return False
        self.last_command_time = now
        self.motion_command_active = True
        return True

    def set_emergency_stop(self, active: bool):
        self.emergency_stop = active
        self.motion_command_active = False
        self.last_command_time = None

    def consume_timeout(self, now: float) -> bool:
        if not self.motion_command_active or self.last_command_time is None:
            return False
        if now - self.last_command_time <= self.command_timeout:
            return False
        self.motion_command_active = False
        return True
