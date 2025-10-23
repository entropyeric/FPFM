FPFM - Finger Pressure Force Measurement Paradigm
项目描述
这是一个进行手指压力力量测试的范式，基于PsychoPy、Neuracle NEO(微创硬膜外脑机接口)设备和Runeskee压力传感器。
________________________________________
安装依赖
1.	下载并安装PsychoPy运行环境
StandalonePsychoPy-2025.1.1-win64-py3.8.exe(https://github.com/psychopy/psychopy/releases/download/2025.1.1/StandalonePsychoPy-2025.1.1-win64-py3.8.exe)
2.	安装Runeskee传感器驱动
在电脑连接Runeskee压力传感器的条件下，安装install/CH341SER_DRIVER.EXE
________________________________________
首次运行指南
1.	硬件连接
•	使用USB线连接Neuracle Trigger Box的trigger接口
•	连接Runeskee压力传感器
•	通过设备管理器记录下两个设备的COM端口号
2.	配置文件设置
打开config.yml并修改以下参数：
•	psychopy_py: 替换为刚刚安装的PsychoPy的Python路径
•	serial_port: 替换为Runeskee传感器的COM端口
•	trigger_com: 替换为Trigger Box的COM端口
•	screen_size: 根据实际需求调整屏幕尺寸
3.	压力传感器校准
•	要求被试全力按压Runeskee压力传感器并记录最大值
•	max_force: 设置为最大值的1.25倍
•	top_force: 设置为远超被试全力按压的值（最高6000g）
4.	运行实验
在VSCode中运行launch_pipeline.py：
•	程序将自动运行4个子范式：
1.	最大力测试
2.	80%维持力测试
3.	40%维持力测试
4.	20%维持力测试
•	屏幕显示：红线为目标力，动态蓝柱为当前出力
•	每个范式重复5次
5.	数据保存
测试结果自动保存在mat_data/目录下
6.	结果验证
使用verify/read_mat.ipynb可视化结果，确认数据记录正确性
________________________________________
注意事项
非同步采集模式
若不需要进行颅内脑电与力量数据的同时采集：
•	在config.yml中将synchronized_with_eeg设置为false
•	可跳过步骤1和2中与Trigger Box相关的操作

FPFM/
├── mat_data/          # 实验数据存储
├── verify/            # 数据验证工具
│   └── read_mat.ipynb # 结果可视化
├── install/           # 驱动安装文件
│   └── CH341SER_DRIVER.EXE
├── config.yml         # 主配置文件
└── launch_pipeline.py # 主执行文件


________________________________________________________________________________
English Version
Project Description
This is a finger pressure force measurement paradigm based on PsychoPy, Neuracle NEO (minimally invasive epidural BCI) device and Runeskee pressure sensor.
________________________________________
Installation Dependencies
1.	Download and install PsychoPy runtime environment
StandalonePsychoPy-2025.1.1-win64-py3.8.exe(https://github.com/psychopy/psychopy/releases/download/2025.1.1/StandalonePsychoPy-2025.1.1-win64-py3.8.exe)
2.	Install Runeskee sensor driver
With Runeskee pressure sensor connected to your computer, install install/CH341SER_DRIVER.EXE
________________________________________
First Run Guide
1.	Hardware Setup
•	Connect Neuracle Trigger Box's trigger interface via USB
•	Connect Runeskee pressure sensor
•	Record COM port numbers for both devices via Device Manager
2.	Configuration Setup
Open config.ymland modify:
•	psychopy_py: Path to PsychoPy's Python installation
•	serial_port: COM port for Runeskee sensor
•	trigger_com: COM port for Trigger Box
•	screen_size: Adjust according to display requirements
3.	Sensor Calibration
•	Have subject press sensor with maximum force and record value
•	max_force: Set to 1.25× maximum recorded value
•	top_force: Set to value far exceeding subject's max (max 6000g)
4.	Run Experiment
Execute launch_pipeline.pyin VSCode:
•	Automatically runs 4 sub-paradigms:
1.	Maximum force test
2.	80% sustained force
3.	40% sustained force
4.	20% sustained force
•	Screen display: Red line = target force, Blue bar = current force
•	Each paradigm repeats 5 times
5.	Data Saving
Results automatically saved in mat_data/directory
6.	Result Verification
Use verify/read_mat.ipynbto visualize results and confirm data integrity
________________________________________
Important Notes
Non-synchronized Mode
If intracranial EEG and force data synchronization is not required:
•	Set synchronized_with_eegto falsein config.yml
•	Skip Trigger Box-related steps in sections 1 and 2

FPFM/
├── mat_data/          # Experiment data storage
├── verify/            # Data verification tools
│   └── read_mat.ipynb # Results visualization
├── install/           # Driver installation files
│   └── CH341SER_DRIVER.EXE
├── config.yml         # Main configuration
└── launch_pipeline.py # Main executable





