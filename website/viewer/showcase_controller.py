"""Original five-asset demo setpoints, evaluated without executing asset code.

These functions reproduce the supplied demo.py controller. They only return
actuator controls; the unchanged MJCF model and MuJoCo determine the motion.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np


class ShowcaseController:
    def __init__(self, model, resource_root):
        root = Path(resource_root)
        metadata = json.loads((root / "asset.json").read_text(encoding="utf-8"))
        self.identity = metadata["id"]
        self.cycle_seconds = float(metadata["cycle_seconds"])
        if self.identity not in {"camera", "phone", "globe", "ladder", "carousel"}:
            raise ValueError("Automatic demonstration is only available for the five Overview assets.")
        if not math.isfinite(self.cycle_seconds) or self.cycle_seconds <= 0:
            raise ValueError("The demonstration cycle must be positive and finite.")
        self.names = [model.actuator(i).name for i in range(model.nu)]
        if self.identity in {"ladder", "globe", "carousel"}:
            profile = json.loads((root / "control_profile.json").read_text(encoding="utf-8"))
            self.times = np.asarray(profile["time"], dtype=float)
            self.controls = np.asarray(profile["ctrl"], dtype=float)
            if (self.times.ndim != 1 or len(self.times) < 2
                    or self.controls.shape != (len(self.times), model.nu)
                    or not np.isfinite(self.times).all() or not np.isfinite(self.controls).all()
                    or not (np.diff(self.times) > 0).all()):
                raise ValueError("The demonstration control profile is invalid.")
        elif self.identity == "camera":
            self.rates = {}
            for joint, actuator, rate, gain in (
                ("mode_dial", "dial_virtual_hand", math.tau / 8, .01),
                ("secondary_dial", "secondary_dial_virtual_hand", math.tau / 6, .01),
                ("focus_ring", "focus_virtual_hand", math.tau / 12, .02),
            ):
                address = model.joint(joint).dofadr[0]
                self.rates[actuator] = (rate * (1 + model.dof_damping[address] / gain)
                                        + model.dof_frictionloss[address] / gain)

    def __call__(self, simulation_time):
        t = float(simulation_time)
        if self.identity in {"ladder", "globe", "carousel"}:
            return np.array([np.interp(t % self.cycle_seconds, self.times, self.controls[:, i])
                             for i in range(len(self.names))])
        if self.identity == "phone":
            t %= 20.0
            previous = np.array([math.pi, math.pi])
            phases = ((2., (180, 180)), (3.2, (0, 180)), (.4, (0, 180)),
                      (3.2, (0, 0)), (2.8, (0, 0)), (3.2, (0, 180)),
                      (.4, (0, 180)), (3.2, (180, 180)), (1.6, (180, 180)))
            for duration, target in phases:
                goal = np.deg2rad(target)
                if t <= duration:
                    x = t / duration
                    weight = x * x * x * (10 + x * (-15 + 6 * x))
                    return previous + (goal - previous) * weight
                previous = goal
                t -= duration
            return previous
        phase = t % 2
        values = dict(self.rates)
        values["screen_virtual_hand"] = 2.82 * .5 * (1 - math.cos(math.tau * t / 24))
        values["zoom_virtual_hand"] = .006 * (1 - math.cos(math.tau * t / 6))
        values["virtual_finger_press_force"] = (.30 * self._smooth((phase - .12) / .43)
                                                 * (1 - self._smooth((phase - .86) / .38)))
        return np.array([values[name] for name in self.names])

    @staticmethod
    def _smooth(value):
        value = max(0, min(1, value))
        return value * value * (3 - 2 * value)
