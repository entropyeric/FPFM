# 修改版，于20250911，增加了Top Force，修正了trigger——LWZ
import socket
try:
    from .triggerBox import TriggerNeuracle
except Exception:
    from triggerBox import TriggerNeuracle
import time
import struct
import scipy.io as scio
import numpy as np
from datetime import datetime

class FingerForce:
    def __init__(self, is_socket=True):
        self.is_socket = is_socket
        if is_socket:
            SOCKET_HOST = '127.0.0.1'
            SOCKET_PORT = 12345
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.settimeout(0.0005)  # 设置短超时（非阻塞关键）
            self.socket.connect((SOCKET_HOST, SOCKET_PORT))
        # --- configurable parameters (defaults) ---
        self.synchronized_with_eeg = False  # 是否与EEG同步
        # 统一命名（与 launcher 的补丁规则一致）
        self.Max_Force = 700  # 能达成的最大力值
        self.Top_Force = 2000  # 无法达成的最大力值

        # Load overrides from environment
        import os as _os
        _mf = _os.environ.get('FPFM_MAX_FORCE')
        if _mf:
            try:
                self.Max_Force = int(_mf)
            except Exception:
                pass
        _tf = _os.environ.get('FPFM_TOP_FORCE')
        if _tf:
            try:
                self.Top_Force = int(_tf)
            except Exception:
                pass
        _sync = _os.environ.get('FPFM_SYNC_EEG')
        if _sync is not None:
            self.synchronized_with_eeg = (_sync.strip() == '1') or (_sync.strip().lower() in ('true','yes','on'))

        # 触发器初始化：确保属性始终存在
        self.trigger = None
        if self.synchronized_with_eeg:
            _port = _os.environ.get('FPFM_TRIGGER_COM') or 'COM6'
            try:
                self.trigger = TriggerNeuracle(port=_port)
                print(f"Trigger initialized on {_port}")
            except Exception as e:
                print(f"Trigger init failed: {e}")
                self.trigger = None
        self.Fid = 3
        self.sensor_value = 0
        self.Target_Force = []

    def send_trigger(self, trigger_value):
        # 若不同步EEG，则直接返回（不发送trigger）
        if not getattr(self, 'synchronized_with_eeg', True):
            return
        # 向triggerbox发送trigger
        try:
            if self.trigger is not None:
                self.trigger.send_trigger(trigger_value)
                print(f"Sent trigger via triggerbox: {trigger_value}")
        except Exception as e:
            print(f"Triggerbox error: {e}")
        
        # 向socket发送trigger
        try:
            self.socket.sendall(struct.pack('i', trigger_value))
            print(f"Sent trigger via socket: {trigger_value}")
        except Exception as e:
            print(f"Error sending trigger via socket: {e}")

    def receive_sensor_value(self, prog, bmax=None):
        # 接收传感器值
        value = receive_sensor_(self.socket)
        
        # 更新传感器值（如果新值有效）
        if value is not None:
            self.sensor_value = value
        # 如果新值无效，使用之前保存的有效值
        else:
            value = self.sensor_value  # 使用保存的有效值
        
        print(f"Recv sensor value: {value}")
        # 根据当前Fid选择力值基准
        if self.Fid == 3:  # 第一个block使用Top_Force
            force_base = self.Top_Force
        else:  # 后续blocks使用Max_Force
            force_base = self.Max_Force
            
        # 计算除数
        divisor = bmax if bmax is not None else force_base
        
        # 安全检查：避免除零错误
        if divisor == 0:
            print("警告: 除数为零，使用默认值 0")
            progress_value = 0
        else:
            progress_value = value / divisor
        
        # 设置进度条
        prog.setProgress(progress_value)
        
        # 返回值
        return progress_value


    def get_target_value(self, length=200, n_basis=14):
        seq = rbf_sequence(length=length, n_basis=n_basis)
        self.Target_Force.append(seq)
        return seq


    def save_to_mat(self):
        scio.savemat('target_force_{}.mat'.format(datetime.now().strftime("%Y%m%d")), 
                     {'target_force': np.array(self.Target_Force)})


def receive_sensor_(conn):
    buffer = b""  # 字节缓冲区
    while True:
        try:
            chunk = conn.recv(1024)  # 每次最多收1KB
            if not chunk:  # 连接断开
                break
            
            buffer += chunk
            if b'\n' in buffer:  # 检测到完整消息
                line, buffer = buffer.split(b'\n', 1)  # 拆分出第一行
                try:
                    value = int(line.decode('utf-8'))  # 字符串转整数
                    print(f"Recv: {value}")
                    return value
                except ValueError:
                    print(f"无效数据: {line}")
        except Exception as e:
            print(f"接收错误: {e}")
            break
    return None  # 失败时返回None


def rbf_sequence(length=200, n_basis=14, x_range=(-0.5, 0.5), y_range=(-0.4, 0.4), seed=None):
    x = np.linspace(x_range[0], x_range[1], length)
    centers = np.random.uniform(x_range[0]+0.1, x_range[1], n_basis)
    widths = np.random.uniform(0.02, 0.07, n_basis)
    weights = np.random.uniform(y_range[0], y_range[1], n_basis)
    y = np.zeros_like(x)
    for c, w, a in zip(centers, widths, weights):
        y += a * np.exp(-0.5 * ((x - c) / w) ** 2)
    return np.clip(y, -0.5, 0.5)
