name: MDev            ## Name of the scope
type: microscope      ## Type of device -> Selection of the abstraction

## Hardware configuration -----
devices:
  pico: 
    description: "Main microcontroller connected to illumination source and tandh sensor."
    kind: hive.processorgroups.micropython.SerialMPDevice
    args: []
    kwargs:
        name: pico
        search_name: picodev
        connect: "autoconnect"
        exec_main: True
        handshake: True
  cam:
    description: Microscope main camera.
    kind: detectors.cameras.rpi_hq_picam2.Camera
    args: []
    kwargs: {}

  trap: 
    description: "Microfluidic device that contains sample."
    kind: hive.physical.PhysicalObject
    args: [trap]
    kwargs:
      persistent: True
  sample:
    description: "Cell culture"
    kind: hive.physical.PhysicalObject
    args: [sample]
    kwargs:
      persistent: False

  pico2: 
    description: "Other pico device with the spectrum sensor."
    kind: hive.processorgroups.micropython.SerialMPDevice
    args: []
    kwargs:
        name: pico2
        search_name: pico_on_a_spectrum
        connect: "autoconnect"
        exec_main: True
        handshake: True



lit: ## Additional information that is bound to the Proxy as a physical object.
  kind: proxy
  args: []
  kwargs: {}
  attribs: {channels: [627.5, 525.0 , 467.5], 
            control: voltage_pwm_common_anode, 
            form_factor: 5mm, 
            identifier: "ThorLabs LEDRGBE"}






abstraction: ## Abstractions are ways of interpreting the hardware in different ways.
  microscope:
    cam: detector
    lit: actuator
    trap: physical-persistent
    sample: physical
  telescope:
    cam: detector
    compass: detector
    gps: detector
  computing-cluster:
    m1 : processorgroups.linux
    m2 : processorgroups.linux
    m3 : processorgroups.linux
    m4 : processorgroups.linux
    m5 : processorgroups.linux
    m6 : processorgroups.linux
    m7 : processorgroups.linux
    m8 : processorgroups.linux
    vwr: processorgroups.linux
  control-terminal1:
    pico_keypad:
      type: processorgroup.micropython.SerialMPDevice
    pico_motorset_2ch:
      type: processorgroup.micropython.SerialMPDevice
  uv_lamp:
    array1:
      type: rpi-gpio-digital-out
      pin: 14
    array2: 
      type: rpi-gpio-digital-out
      pin: 14
    gate_sensor:
      type: ir_proximity_sensor


config:
  expdir: "~/experiments"
  autostart_cli_after_reboot: true
  ui_mode: interactive
  venv: 
    active: true
    command: source ~/opt/miniconda3/bin/activate
    name: trappy
  git_sync: false
  git_dependencies:
    https://github.com/Trappy-Scopes/pico_firmware: "~/code/Trappy-Scopes/pico_firmware"
  set_wallpaper: false
  log_level: 10
  file_server:
    active: false
    destination: "{date}"
    server: 172.22.63.19
    share: eyespot
    username: TS
    password: Chlamy_123
  startup_scripts:
    - scripts/alignmenttools/framealignmnet.py
    - scripts/longterm/mjpeg_continuous_autosplit.py

