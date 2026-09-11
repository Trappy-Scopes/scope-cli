from picamera2 import Picamera2, Preview
from picamera2.encoders import H264Encoder
import time
import os
import pandas as pd
from openpyxl import load_workbook
import gc
#import numpy as np

# recording params - these are fixed
time_all =24*60*60. # time of all recordings - 36 hours
total_time = 1.*60*60. #in seconds - 1 hour each
time_each = 1*60*10. #in seconds - ten minutes each
#time_interval = 1.*1*60.  # time interval between recordings
time_interval=0.
iterations = int(total_time/time_each) #number of split videos
iterations_all = int(time_all/total_time)

# create folder to save video and metadata
folder = "record1"
if not(os.path.exists(folder)):
    os.mkdir(folder)
os.chdir(folder)
TIMESTAMP_FILE = f"timestamps_{folder}.txt"

# camera and video controls
# camera and video controls
fps=20.
framelimit=int(1000000/fps)
res_x = 1920
res_y = 1080
exposure_time=50000
awb_enable = False
ae_enable = False
brightness = 0.3
analogue_gain=3
contrast = 2.5
colour_gains = (0.,0.)
sharpness = 1.
saturation = .5
#exposure_value = 5

#"AeExposureMode":"Custom"}
#"FrameDurationLimits":(framelimit,framelimit)
#DigitalGain cannot be set
#"AnalogueGain":1000
#ColourGains":(0.,32.)
#"Contrast":32.0

# ---------------------------------------------------------
# initialize picamera2 object
picam2 = Picamera2()

#define a dictionary with the controls to save in file
controls={"FrameRate":fps,
"ExposureTime":exposure_time,
"AwbEnable":awb_enable,
"AeEnable":ae_enable,
"AnalogueGain":analogue_gain,
"Brightness":brightness,
"Contrast":contrast,
"ColourGains":colour_gains,
"Sharpness":sharpness,
"Saturation":saturation}

times={"TimeEach":time_each, "TimeTotal": total_time,
"TimeAll": time_all, "TimeInterval": time_interval}
#"ExposureValue":exposure_value}


# create video configuration
picam2.create_video_configuration({"size":(res_x,res_y)},
controls=controls)

#the video configuration controls need to be set again - set only the ones in 'controls'
picam2.video_configuration.controls.FrameRate = fps
picam2.video_configuration.controls.ExposureTime = exposure_time
picam2.video_configuration.controls.AwbEnable = awb_enable
picam2.video_configuration.controls.AeEnable = ae_enable
picam2.video_configuration.controls.AnalogueGain = analogue_gain
picam2.video_configuration.controls.Brightness = brightness
picam2.video_configuration.controls.Contrast = contrast
picam2.video_configuration.controls.ColourGains = colour_gains
picam2.video_configuration.controls.Sharpness = sharpness
picam2.video_configuration.controls.Saturation = saturation
#picam2.video_configuration.controls.ExposureValue = exposure_value
#picam2.video_configuration({'size':(res_x,res_y)})
picam2.video_configuration.size = (res_x,res_y)

# to call before start recording - saves the timestamps in a txt file
'''
label=-1
def call_label():
    label += 1
    yield label
'''
    
def write_timestamp(request):
    #label = call_label()
    timestamp = time.time()
    ftimestamps.write(f"{timestamp}\n") 

# metadata file (camera controls and video metadata)
df1 = pd.DataFrame.from_dict(controls, orient='index')
df2 = pd.DataFrame.from_dict(picam2.camera_properties,orient='index')
df3 = pd.DataFrame.from_dict(times,orient='index')
dftotal = pd.concat([df1,df2,df3],ignore_index=False,sort=False)
dftotal.to_csv(f"metadata_{folder}.csv")

# open timestamp file
ftimestamps = open(TIMESTAMP_FILE, 'w')
t=0
#i=0
picam2.pre_callback = write_timestamp
while(t<iterations_all):
    gc.collect()
    #TIMESTAMP_FILE = f"timestamps_{folder}_{label+1}.txt"
    #ftimestamps = open(TIMESTAMP_FILE, 'w')
    i=0
    while(i<iterations):
        picam2.start_and_record_video(f"video{t}_{i}.mp4",duration=time_each)
        i+=1
    print(f"waiting for {t}, {time_interval} s")
    time.sleep(time_interval)
    t+=1
    #ftimestamps.close() #close timestamp file
    #picam2.start_recording(encoder,f"video{i}.h264")
    #print(picam2.capture_metadata()['SensorTimestamp'])
    #time.sleep(time_each)
    #picam2.stop_recording()
    #print(picam2.camera_properties)

ftimestamps.close() #close timestamp file
