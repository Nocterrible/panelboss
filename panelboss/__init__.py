"""PanelBoss.

Presence-aware monitor power control for Windows: watches a webcam, decides
whether someone is present, and drives the displays into the same DPMS
standby state the power plan uses (SC_MONITORPOWER broadcast), then wakes
them when a person comes back.
"""

__version__ = "0.3.6"
