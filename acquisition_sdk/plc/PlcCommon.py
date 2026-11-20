import os
import socket
import time
from typing import Dict, Optional
# import sys
# # 将项目的根目录添加到 sys.path 中，确保能导入 model 包
# sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
from acquisition_sdk.plc.MovingFrameData import ReceiveMovingFrameData
from model.utils.TomlLoader import TomlLoader
from model.utils.LoggerUtil import logger


START = bytes([0x02, 0x02, 0x02, 0x02])
END = bytes([0x03, 0x03, 0x03, 0x03])
ReadCommon = b'\x02\x02\x02\x02\x01\x03\x03\x03\x03'


class BasePlc:
    def __init__(self, plc_id: str, config: Dict):
        self.id = plc_id
        self.tcp_ip = config["tcp_ip"]
        self.tcp_port = config["tcp_port"]
        self.udp_ip = config["udp_ip"]
        self.udp_port = config["udp_port"]
        self._tcp_socket: Optional[socket.socket] = None
        self._udp_socket: Optional[socket.socket] = None

        read_data_config = TomlLoader.load(os.path.join(os.getcwd(), "model", "tomls", "ReadDataConfig.toml"))
        poll_timeout_ms = float(read_data_config.get("socket_recv_poll_timeout_ms", 50))
        max_attempts = int(read_data_config.get("socket_recv_max_attempts", 3))
        if poll_timeout_ms <= 0 or max_attempts <= 0:
            raise ValueError("Socket接收超时配置必须为正数")
        self.socket_recv_poll_timeout_s = poll_timeout_ms / 1000.0
        self.socket_recv_max_attempts = max_attempts

    def connect(self, connection_type: str = "tcp") -> bool:
        """连接到PLC，连接类型可选 'tcp' 或 'udp'，返回是否成功"""
        max_retries = 1
        for attempt in range(max_retries):
            try:
                if connection_type == "tcp":
                    self._tcp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    self._tcp_socket.connect((self.tcp_ip, self.tcp_port))
                    logger.info(f"PLC tcp:  {self.tcp_ip}:{self.tcp_port} connected successfully")
                    return True
                elif connection_type == "udp":
                    self._udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                    self._udp_socket.bind((self.udp_ip, self.udp_port))
                    logger.info(f"PLC udp:  {self.udp_ip}:{self.udp_port} connected successfully")
                    return True
                else:
                    raise ValueError("Unsupported connection type. Choose 'tcp' or 'udp'.")
            except (socket.error, ValueError) as e:
                if attempt < max_retries - 1:
                    logger.warning(f"PLC connection attempt {attempt+1} failed: {str(e)}. Retrying...")
                    time.sleep(70)  # 等待70秒后重试
                else:
                    logger.error(f"PLC connection failed after {max_retries} attempts: {str(e)}")
                    return False
        return False

    def disconnect(self, connection_type: str = "tcp") -> None:
        """断开与PLC的连接，连接类型可选 'tcp' 或 'udp'"""
        if connection_type == "tcp" and self._tcp_socket:
            self._tcp_socket.close()
            self._tcp_socket = None
            logger.info("TCP connection to PLC closed.")
        elif connection_type == "udp" and self._udp_socket:
            self._udp_socket.close()
            self._udp_socket = None
            logger.info("UDP connection to PLC closed.")
        else:
            raise ValueError(f"Cannot disconnect. No {connection_type.upper()} connection found.")

    def _read_data(self, check_start, check_end, connection_type: str = "tcp") -> bytes:
        """接收数据, 确保使用时已初始化socket"""
        if connection_type == "tcp" and not self._tcp_socket:
            raise ConnectionError("TCP socket not initialized")

        if connection_type == "tcp" and self._tcp_socket is not None:
            active_socket = self._tcp_socket
        elif connection_type == "udp" and self._udp_socket is not None:
            active_socket = self._udp_socket
        else:
            raise ConnectionError("connection_type is not supported")

        buffer = bytearray()
        total_timeout = self.socket_recv_poll_timeout_s * self.socket_recv_max_attempts
        deadline = time.monotonic() + total_timeout
        previous_timeout = active_socket.gettimeout()
        try:
            if connection_type == "tcp":
                active_socket.sendall(ReadCommon)

            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise socket.timeout(f"PLC响应超时，等待约{total_timeout:.3f}秒")

                active_socket.settimeout(min(self.socket_recv_poll_timeout_s, remaining))
                try:
                    if connection_type == "tcp":
                        chunk = active_socket.recv(4096)
                    else:
                        chunk, _ = active_socket.recvfrom(4096)
                except socket.timeout:
                    if time.monotonic() >= deadline:
                        raise socket.timeout(f"PLC响应超时，等待约{total_timeout:.3f}秒")
                    continue

                if not chunk:
                    raise ConnectionError("PLC connection closed")

                buffer.extend(chunk)
                if check_start(buffer) and check_end(buffer):
                    return bytes(buffer)
        finally:
            active_socket.settimeout(previous_timeout)

    def scan(self, connection_type="tcp", **kwargs):
        """
        接收并解析PLC数据帧
        Args:
            connection_type: 连接类型 'tcp' 或 'udp'
            **kwargs: 动态列表长度覆盖, 如 AllLidarData_count=6
        Returns:
            ReceiveMovingFrameData 实例
        """
        raw = self._read_data(self._check_start, self._check_end, connection_type)
        payload = raw[len(START):-len(END)]
        frame, _ = ReceiveMovingFrameData.from_bytes(payload, **kwargs)
        return frame

    def _check_start(self, data):
        return data.startswith(START)

    def _check_end(self, data):
        return data.endswith(END)


class PlcManager:
    def __init__(self, config_path: str):
        self.config = TomlLoader.load(config_path)
        self.plc: Dict[str, BasePlc] = {}
        self._init_plc()
        self.get_plc("1")

    def _init_plc(self):
        for plc_id, cfg in self.config.items():
            if plc_id not in ["1", "2", "3", "4", "5"]:
                continue
            self.plc[plc_id] = BasePlc(plc_id, cfg)

    def get_plc(self, plc_id: str) -> BasePlc:
        if plc_id not in self.plc:
            raise ValueError(f"Invalid plc ID: {plc_id}")
        return self.plc[plc_id]
