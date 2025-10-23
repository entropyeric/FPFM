#配套20250911修改版——LWZ
import serial
import socket
import threading
import time
import numpy as np
from scipy.io import savemat, loadmat
from datetime import datetime
import struct
import queue
import os
import errno  # 关键错误码处理
import sys


# 配置参数
SERIAL_PORT = 'COM5'  # recorder COM
BAUD_RATE = 9600            # 波特率
REQUEST_DATA = bytes.fromhex('01 03 00 00 00 01 84 0A')  # 请求指令
SAMPLE_INTERVAL = 0.05      # 50ms采样周期

SOCKET_HOST = '127.0.0.1'   # Socket主机
SOCKET_PORT = 12345         # Socket端口

# Allow overriding via environment variables
_env_port = os.environ.get('FPFM_SERIAL_PORT')
if _env_port:
    SERIAL_PORT = _env_port

# Control/shutdown settings
CTRL_HOST = '127.0.0.1'
CTRL_PORT = int(os.environ.get('FPFM_CTRL_PORT', '12346'))
STOP_EVENT = threading.Event()

SAVE_INTERVAL = 600          # 超过10分钟自动保存一次数据
MAT_FILENAME = 'sensor_data.mat'  # 保存文件名


class DataRecorder:
    def __init__(self, hand='R'):
        self.sensor_data = []
        self.trigger_data = []
        self.timestamps = []
        self.hand = hand
        self.lock = threading.Lock()
        # 确保保存目录存在
        self.mat_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'mat_data')
        os.makedirs(self.mat_dir, exist_ok=True)
        
    def add_data(self, sensor_value, trigger, timestamp):
        with self.lock:
            self.sensor_data.append(sensor_value)
            self.trigger_data.append(trigger)
            self.timestamps.append(timestamp)
    
    def get_next_mat_filename(self, prefix="FinFor"):
        today = datetime.now().strftime("%Y%m%d")
        idx = 1
        while True:
            fname = f"{prefix}{self.hand}_{today}-{idx}.mat"
            full_path = os.path.join(self.mat_dir, fname)
            if not os.path.exists(full_path):
                return full_path
            idx += 1

    def save_to_mat(self, filename="FinFor"):
        with self.lock:
            if not self.sensor_data:
                return

            filename = self.get_next_mat_filename(prefix=filename)

            # 准备保存的数据
            data_to_save = {
                'sensor_data': np.array(self.sensor_data),
                'trigger_data': np.array(self.trigger_data),
                'timestamps': np.array(self.timestamps),
                'description': 'Sensor data with corresponding triggers',
                'created': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
            if filename.endswith("ForTra.mat"):
                try:
                    Tar_for = loadmat('target_force_{}.mat'.format(datetime.now().strftime("%Y%m%d")))
                    data_to_save['target_force'] = Tar_for['target_force']
                    print('Target force data loaded from file.')
                except FileNotFoundError:
                    print('Target force file not found, skipping.')
            
            try:
                savemat(filename, data_to_save)
                print(f"Data saved to {filename}")
                
                # 清空已保存的数据
                self.sensor_data = []
                self.trigger_data = []
                self.timestamps = []
            except Exception as e:
                print(f"Error saving to .mat file: {e}")



def serial_worker(ser, data_recorder, data_queue, sensor_queue):
    last_sample_time = time.time()
    current_trigger = -1
    timestamp = time.time()
    alpha = 0.0  # 初始化alpha
    Kp = 0.7     # 
    Ki = 0.1
    error_integral = 0.0  # 积分误差初始化
    print('****开始记录压力数据****')
    
    while not STOP_EVENT.is_set():
        try:
            # 发送请求数据
            ser.write(REQUEST_DATA)
            
            # 读取响应数据 (假设响应为7字节)
            response = ser.read(7)
            if len(response) == 7:
                sensor_value = struct.unpack('>H', response[3:5])[0]
                print('response:  ', response)
                # 获取当前trigger值
                try:
                    current_trigger = data_queue.get_nowait()
                except queue.Empty:
                    pass
                
                # 记录数据
                interval = time.time() - timestamp
                timestamp = time.time()
                data_recorder.add_data(sensor_value, current_trigger, timestamp)
                # 新增：将最新sensor_value放入队列（非阻塞，队列满则丢弃旧的）
                if sensor_queue.full():
                    try:
                        sensor_queue.get_nowait()
                    except queue.Empty:
                        pass
                if not STOP_EVENT.is_set():
                    sensor_queue.put(sensor_value)
                
                # 通过socket发送数据 (可选)
                if 'socket_conn' in globals():
                    try:
                        globals()['socket_conn'].sendall(response)
                    except:
                        pass
                
                error = interval - SAMPLE_INTERVAL
                error_integral += error
                alpha += Kp * error + Ki * error_integral  # 比例-积分控制
                alpha = min(max(alpha, -SAMPLE_INTERVAL/2), SAMPLE_INTERVAL/2)

                # 控制采样频率
                elapsed = time.time() - last_sample_time
                sleep_time = max(0, SAMPLE_INTERVAL - elapsed - alpha)
                time.sleep(sleep_time)
                last_sample_time = time.time()
                
        except serial.SerialException as e:
            print(f"Serial error: {e}")
            break
        except Exception as e:
            print(f"Error in serial worker: {e}")


def socket_server(data_queue, sensor_queue):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind((SOCKET_HOST, SOCKET_PORT))
            s.listen(1)
            s.settimeout(1.0)  # 轮询停止事件
            print(f"Socket server listening on {SOCKET_HOST}:{SOCKET_PORT}")
            
            conn = None
            addr = None
            while not STOP_EVENT.is_set():
                try:
                    conn, addr = s.accept()
                    break
                except socket.timeout:
                    continue
            if STOP_EVENT.is_set():
                return
            conn.setblocking(False)  # 设置为非阻塞
            globals()['socket_conn'] = conn
            print(f"Connected by {addr}")
            
            while not STOP_EVENT.is_set():
                # 接收trigger数据 (假设trigger是4字节整数)*********
                try:
                    trigger = conn.recv(4)
                    if len(trigger) == 4:
                        trigger_value = struct.unpack('i', trigger)[0]
                        # 清空队列，只保留最新trigger
                        while not data_queue.empty():
                            try:
                                data_queue.get_nowait()
                            except queue.Empty:
                                break
                        data_queue.put(trigger_value)
                        print(f"Received trigger: {trigger_value}")
                    elif len(trigger) == 0:
                        print("Socket closed by client (recv)")
                        break
                        
                except socket.error as e:
                    if e.errno == errno.EAGAIN or e.errno == errno.EWOULDBLOCK:
                        pass
                    else:
                        print(f"真正的Socket错误: {e}")
                        raise  # 其他错误向上抛出

                # 发送最新sensor_value给客户端*********
                try:
                    
                    if sensor_queue.empty():
                        sensor_value = 0  # 或其他默认值
                    else:
                        sensor_value = sensor_queue.get_nowait()
                    conn.sendall(struct.pack('i', sensor_value))
                    print(f"Sent sensor value: {sensor_value}")
                except Exception as e:
                    print(f"Socket send error: {e}")
                    break
                    
        except Exception as e:
            print(f"Socket server error: {e}")
        finally:
            if 'socket_conn' in globals():
                globals()['socket_conn'].close()


def control_server():
    """A simple control server to request graceful shutdown and saving."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as cs:
        cs.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            cs.bind((CTRL_HOST, CTRL_PORT))
            cs.listen(1)
            cs.settimeout(1.0)
            print(f"Control server listening on {CTRL_HOST}:{CTRL_PORT}")
            while not STOP_EVENT.is_set():
                try:
                    conn, _ = cs.accept()
                    with conn:
                        try:
                            data = conn.recv(64)
                            print(f"Control received: {data}")
                        except Exception:
                            pass
                        STOP_EVENT.set()
                        break
                except socket.timeout:
                    continue
        except Exception as e:
            print(f"Control server error: {e}")


def auto_save_worker(data_recorder):
    while not STOP_EVENT.is_set():
        time.sleep(SAVE_INTERVAL)
        try:
            data_recorder.save_to_mat()
        except Exception as e:
            print(f"Auto-save error: {e}")


def trigger_receiver(conn, data_queue):
    while True:
        try:
            trigger = conn.recv(4)
            if len(trigger) == 4:
                trigger_value = struct.unpack('i', trigger)[0]
                # 清空队列，只保留最新trigger
                while not data_queue.empty():
                    try:
                        data_queue.get_nowait()
                    except queue.Empty:
                        break
                data_queue.put(trigger_value)
                print(f"Received trigger: {trigger_value}")
            elif len(trigger) == 0:
                print("Socket closed by client (recv)")
                break
        except Exception as e:
            print(f"Socket receive error: {e}")
            break

def sensor_sender(conn, sensor_queue):
    while not STOP_EVENT.is_set():
        try:
            if sensor_queue.empty():
                sensor_value = 0
            else:
                sensor_value = sensor_queue.get_nowait()
            # conn.sendall(struct.pack('>i', sensor_value))
            data_str = f"{sensor_value}\n"  # 添加换行符作为消息分隔符
            conn.sendall(data_str.encode('utf-8'))  # 编码为字节流发送
        except Exception as e:
            print(f"Socket send error: {e}")
            break
        time.sleep(0.1)  # 100ms周期

def main():
    if len(sys.argv) > 1:
        hand = sys.argv[1]  # 第一个用户参数
        filename = sys.argv[2] # 第二个用户参数
    else:
        print('请传参')
        return

    # 启动控制服务器（用于优雅退出）
    ctrl_thread = threading.Thread(target=control_server, daemon=True)
    ctrl_thread.start()

    # 初始化串口
    try:
        ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
        print(f"Serial port {SERIAL_PORT} opened")
    except serial.SerialException as e:
        print(f"Failed to open serial port: {e}")
        return

    # 启动Socket服务器，等待连接
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((SOCKET_HOST, SOCKET_PORT))
        s.listen(1)
        s.settimeout(1.0)
        print(f"Socket server listening on {SOCKET_HOST}:{SOCKET_PORT}")

        conn = None
        addr = None
        # 等待客户端连接，支持停止
        while not STOP_EVENT.is_set():
            try:
                conn, addr = s.accept()
                break
            except socket.timeout:
                continue
        if STOP_EVENT.is_set():
            try:
                ser.close()
            except Exception:
                pass
            # 保存已有数据
            try:
                # 没有数据记录器时跳过
                pass
            except Exception:
                pass
            return
        print(f"Connected by {addr}")

        # 初始化数据记录器和队列
        data_recorder = DataRecorder(hand)
        data_queue = queue.Queue()
        sensor_queue = queue.Queue(maxsize=1)  # 只保留最新值

        # 启动自动保存线程
        save_thread = threading.Thread(target=auto_save_worker, args=(data_recorder,), daemon=True)
        save_thread.start()

        # 启动trigger接收线程
        trigger_thread = threading.Thread(target=trigger_receiver, args=(conn, data_queue), daemon=True)
        trigger_thread.start()

        # 启动sensor数据发送线程
        sender_thread = threading.Thread(target=sensor_sender, args=(conn, sensor_queue), daemon=True)
        sender_thread.start()

        # 主线程运行串口工作器
        try:
            serial_worker(ser, data_recorder, data_queue, sensor_queue)
        except KeyboardInterrupt:
            print("Program terminated by user")
        finally:
            STOP_EVENT.set()
            try:
                ser.close()
            except Exception:
                pass
            try:
                conn.close()
            except Exception:
                pass
            # 保存数据（包括终止时）
            try:
                data_recorder.save_to_mat(filename=filename)
            except Exception as e:
                print(f"Final save error: {e}")


if __name__ == "__main__":
    main()
