-- ============================================================
-- 智能家居大模型体验平台 - MySQL 8.0 初始化脚本
-- 包含：建库、建表、演示数据（家庭/用户/房间/设备/场景/偏好）
--
-- 用法（在项目根目录执行）：
--   mysql -u root -p < database/init.sql
--   或使用 backend/docker-compose.yml 启动 MySQL 8.0 时自动初始化
--
-- 说明：
--   * 脚本会重建 smart_home 库中的全部业务表，运行前请确认可覆盖。
--   * 演示账号密码统一为 123456（演示模式明文保存，不做哈希与安全校验）。
--   * users.family_id 不建外键：与后端 ORM 保持一致，注册家庭时房主
--     先以 family_id=0 创建，再绑定真实家庭，避免外键循环依赖。
-- ============================================================

SET NAMES utf8mb4;

DROP DATABASE IF EXISTS smart_home;
CREATE DATABASE smart_home DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE smart_home;

-- ============ families 家庭表 ============
CREATE TABLE families (
  id            BIGINT AUTO_INCREMENT PRIMARY KEY,
  name          VARCHAR(64)  NOT NULL COMMENT '家庭名称，如"张三的家"',
  owner_user_id BIGINT       NOT NULL COMMENT '房主用户ID',
  description   TEXT         COMMENT '家庭描述',
  is_active     TINYINT(1)   NOT NULL DEFAULT 1 COMMENT '是否启用（软删除）',
  created_at    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY uk_owner (owner_user_id) COMMENT '一个用户只能是一个家庭的房主',
  INDEX idx_active (is_active)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='家庭表';

-- ============ users 用户表 ============
CREATE TABLE users (
  id         BIGINT AUTO_INCREMENT PRIMARY KEY,
  username   VARCHAR(64)  NOT NULL UNIQUE COMMENT '用户名，登录用',
  password   VARCHAR(255) NOT NULL COMMENT '登录密码（演示模式明文保存）',
  nickname   VARCHAR(64)  NOT NULL COMMENT '昵称，前端展示',
  role       ENUM('owner','resident','guest') NOT NULL DEFAULT 'guest' COMMENT '角色：房主/住户/访客',
  family_id  BIGINT       NOT NULL COMMENT '所属家庭ID，注册流程中允许临时为0',
  avatar_url VARCHAR(255) COMMENT '头像URL',
  created_at DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  INDEX idx_family (family_id),
  INDEX idx_role (role)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='用户表';

-- ============ rooms 房间表 ============
CREATE TABLE rooms (
  id          BIGINT AUTO_INCREMENT PRIMARY KEY,
  family_id   BIGINT       NOT NULL COMMENT '所属家庭ID',
  name        VARCHAR(64)  NOT NULL COMMENT '房间名称',
  description TEXT         COMMENT '房间描述',
  icon        VARCHAR(64)  DEFAULT 'home' COMMENT '图标标识',
  sort_order  INT          NOT NULL DEFAULT 0 COMMENT '排序权重',
  is_active   TINYINT(1)   NOT NULL DEFAULT 1 COMMENT '是否启用（软删除）',
  created_at  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  INDEX idx_family_active (family_id, is_active),
  INDEX idx_family_sort (family_id, sort_order),
  CONSTRAINT fk_rooms_family FOREIGN KEY (family_id) REFERENCES families(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='房间表';

-- ============ devices 设备表 ============
CREATE TABLE devices (
  id          BIGINT AUTO_INCREMENT PRIMARY KEY,
  family_id   BIGINT       NOT NULL COMMENT '所属家庭ID',
  name        VARCHAR(64)  NOT NULL COMMENT '设备名称',
  type        VARCHAR(32)  NOT NULL COMMENT 'air_conditioner/robot_vacuum/light/curtain/speaker/tv/air_purifier/humidifier/water_heater/washer/fridge/door_lock/camera',
  room_id     BIGINT       NOT NULL COMMENT '所属房间ID',
  brand       VARCHAR(64)  COMMENT '品牌',
  model       VARCHAR(64)  COMMENT '型号',
  status      JSON         NOT NULL COMMENT '设备状态JSON，结构因类型而异',
  is_active   TINYINT(1)   NOT NULL DEFAULT 1 COMMENT '是否启用（软删除）',
  created_at  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  INDEX idx_family (family_id),
  INDEX idx_family_room (family_id, room_id),
  INDEX idx_family_type (family_id, type),
  INDEX idx_active (is_active),
  CONSTRAINT fk_devices_family FOREIGN KEY (family_id) REFERENCES families(id) ON DELETE CASCADE,
  CONSTRAINT fk_devices_room FOREIGN KEY (room_id) REFERENCES rooms(id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='设备表';

-- ============ conversations 对话历史表 ============
CREATE TABLE conversations (
  id           BIGINT AUTO_INCREMENT PRIMARY KEY,
  family_id    BIGINT       NOT NULL COMMENT '所属家庭ID',
  user_id      BIGINT       NOT NULL COMMENT '用户ID',
  role         ENUM('user','assistant','tool') NOT NULL COMMENT '消息角色',
  content      TEXT         NOT NULL COMMENT '消息内容',
  tool_calls   JSON         COMMENT 'LLM返回的工具调用（role=assistant时）',
  tool_call_id VARCHAR(64)  COMMENT '工具调用ID（role=tool时）',
  tool_name    VARCHAR(64)  COMMENT '工具名称（role=tool时）',
  session_id   VARCHAR(64)  NOT NULL COMMENT '会话ID，多轮对话标识',
  created_at   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_family_user_session (family_id, user_id, session_id),
  INDEX idx_session (session_id),
  CONSTRAINT fk_conversations_family FOREIGN KEY (family_id) REFERENCES families(id) ON DELETE CASCADE,
  CONSTRAINT fk_conversations_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='对话历史表';

-- ============ uploaded_files 上传文件表 ============
CREATE TABLE uploaded_files (
  id           BIGINT AUTO_INCREMENT PRIMARY KEY,
  family_id    BIGINT       NOT NULL COMMENT '所属家庭ID',
  user_id      BIGINT       NOT NULL COMMENT '上传用户ID',
  filename     VARCHAR(255) NOT NULL COMMENT '原始文件名',
  file_path    VARCHAR(512) NOT NULL COMMENT '存储路径',
  file_type    VARCHAR(16)  NOT NULL COMMENT 'pdf/docx/txt',
  file_size    BIGINT       NOT NULL COMMENT '字节数',
  content_hash VARCHAR(64)  COMMENT '内容哈希，去重',
  collection   VARCHAR(32)  NOT NULL DEFAULT 'user_documents' COMMENT 'user_documents/family_regulations',
  chunk_count  INT          NOT NULL DEFAULT 0 COMMENT '切片数量',
  status       ENUM('pending','processing','ready','failed') NOT NULL DEFAULT 'pending' COMMENT '处理状态',
  created_at   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_family_user (family_id, user_id),
  INDEX idx_status (status),
  CONSTRAINT fk_files_family FOREIGN KEY (family_id) REFERENCES families(id) ON DELETE CASCADE,
  CONSTRAINT fk_files_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='上传文件表';

-- ============ user_preferences 用户偏好画像表 ============
CREATE TABLE user_preferences (
  user_id     BIGINT PRIMARY KEY,
  preferences JSON         NOT NULL COMMENT '偏好画像JSON',
  updated_at  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  CONSTRAINT fk_preferences_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='用户偏好画像表';

-- ============ device_operation_logs 设备操作日志表 ============
CREATE TABLE device_operation_logs (
  id            BIGINT AUTO_INCREMENT PRIMARY KEY,
  family_id     BIGINT       NOT NULL COMMENT '所属家庭ID',
  device_id     BIGINT       NOT NULL COMMENT '设备ID',
  user_id       BIGINT       COMMENT '操作用户ID（Agent操作时记录触发用户）',
  operation     VARCHAR(32)  NOT NULL DEFAULT 'update' COMMENT 'update/toggle/delete',
  source        ENUM('manual','agent','scheduler') NOT NULL COMMENT '手动/AI/定时任务',
  before_status JSON         COMMENT '变更前状态',
  after_status  JSON         COMMENT '变更后状态',
  description   VARCHAR(255) COMMENT '操作描述',
  created_at    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_family_device (family_id, device_id),
  INDEX idx_family_created (family_id, created_at),
  INDEX idx_user (user_id),
  CONSTRAINT fk_logs_family FOREIGN KEY (family_id) REFERENCES families(id) ON DELETE CASCADE,
  CONSTRAINT fk_logs_device FOREIGN KEY (device_id) REFERENCES devices(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='设备操作日志表';

-- ============ scenes 场景表 ============
CREATE TABLE scenes (
  id          BIGINT AUTO_INCREMENT PRIMARY KEY,
  family_id   BIGINT       NOT NULL COMMENT '所属家庭ID',
  name        VARCHAR(64)  NOT NULL COMMENT '场景名称，如"回家模式"',
  description TEXT         COMMENT '场景描述',
  actions     JSON         NOT NULL COMMENT '场景动作，格式: {"actions": [...]}',
  is_active   TINYINT(1)   NOT NULL DEFAULT 1 COMMENT '是否启用（软删除）',
  created_at  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  INDEX idx_family_active (family_id, is_active),
  CONSTRAINT fk_scenes_family FOREIGN KEY (family_id) REFERENCES families(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='场景表';

-- ============ 演示数据（密码统一 123456） ============

-- 1. 先创建房主用户（family_id 暂为 0，创建家庭后更新）
INSERT INTO users (username, password, nickname, role, family_id) VALUES
  ('owner01', '123456', '房主张三', 'owner', 0),
  ('owner02', '123456', '房主赵六', 'owner', 0),
  ('resident01', '123456', '住户李四', 'resident', 1),
  ('guest01', '123456', '访客王五', 'guest', 1);

-- 2. 创建家庭，owner_user_id 指向房主
INSERT INTO families (name, owner_user_id, description) VALUES
  ('张三的家', 1, '三口之家的智能家居体验环境'),
  ('赵六的家', 2, '单身公寓的智能家居体验环境');

-- 3. 更新房主的 family_id 指向新家庭
UPDATE users SET family_id = 1 WHERE id = 1;
UPDATE users SET family_id = 2 WHERE id = 2;

-- 4. 创建房间（家庭1）
INSERT INTO rooms (family_id, name, description, icon, sort_order) VALUES
  (1, '客厅', '家庭活动中心，含沙发、电视、茶几', 'home', 1),
  (1, '卧室', '主卧，含双人床、衣柜、床头柜', 'bed', 2),
  (1, '厨房', '烹饪区域，含灶台、冰箱、油烟机', 'kitchen', 3),
  (1, '书房', '阅读办公区域', 'book', 4),
  (2, '主卧', '含双人床和衣柜', 'bed', 1),
  (2, '卫生间', '含智能马桶和浴霸', 'bath', 2),
  (2, '阳台', '含晾衣架和绿植', 'balcony', 3);

-- 5. 创建设备（家庭1）
INSERT INTO devices (family_id, name, type, room_id, brand, model, status) VALUES
  (1, '客厅空调', 'air_conditioner', 1, '美的', 'KFR-35',
   '{"power":"off","temperature":26,"mode":"cool","fan_speed":"auto","swing":false}'),
  (1, '卧室空调', 'air_conditioner', 2, '格力', 'KFR-26',
   '{"power":"off","temperature":26,"mode":"cool","fan_speed":"auto","swing":false}'),
  (1, '客厅主灯', 'light', 1, '飞利浦', 'Hue',
   '{"power":"on","brightness":80,"color":"#FFFFFF","mode":"normal"}'),
  (1, '卧室扫地机器人', 'robot_vacuum', 2, '石头', 'S7',
   '{"power":"off","battery":85,"position":{"x":0,"y":0},"cleaning_mode":"auto","status":"idle","dust_bin":30}'),
  (1, '客厅窗帘', 'curtain', 1, '杜亚', 'T820',
   '{"power":"on","position":50,"mode":"manual"}'),
  (2, '主卧空调', 'air_conditioner', 5, '海尔', 'KFR-22',
   '{"power":"off","temperature":25,"mode":"cool","fan_speed":"low","swing":false}'),
  (2, '智能马桶', 'speaker', 6, '松下', 'DL-5220',
   '{"power":"on","volume":20,"playing":false,"source":"local"}'),
  (2, '阳台晾衣架', 'curtain', 7, '好太太', 'GW100',
   '{"power":"on","position":0,"mode":"manual"}');

-- 5.1 扩展设备类型演示数据
INSERT INTO devices (family_id, name, type, room_id, brand, model, status) VALUES
  (1, '客厅电视', 'tv', 1, '小米', 'TV A75', '{"power":"off","volume":20,"channel":1,"input_source":"hdmi1"}'),
  (1, '客厅空气净化器', 'air_purifier', 1, '小米', 'Pro H', '{"power":"off","mode":"auto","fan_speed":"auto","pm25":35,"filter_life":80}'),
  (1, '卧室加湿器', 'humidifier', 2, '智米', 'Smart', '{"power":"off","mode":"auto","target_humidity":55,"water_level":80}'),
  (1, '厨房热水器', 'water_heater', 3, '美的', 'JSQ30', '{"power":"off","temperature":45,"mode":"standard"}'),
  (1, '厨房冰箱', 'fridge', 3, '海尔', 'BCD-470', '{"power":"on","temperature":4,"freezer_temperature":-18,"mode":"smart"}'),
  (1, '入户门锁', 'door_lock', 1, '德施曼', 'Q5M', '{"power":"on","locked":true,"battery":90,"auto_lock":true}'),
  (1, '客厅摄像头', 'camera', 1, '萤石', 'C6', '{"power":"on","recording":false,"motion_detection":true,"night_vision":false}'),
  (2, '主卧电视', 'tv', 5, '海信', 'E7G', '{"power":"off","volume":20,"channel":1,"input_source":"network"}'),
  (2, '卫生间热水器', 'water_heater', 6, '海尔', 'EC6001', '{"power":"off","temperature":45,"mode":"eco"}'),
  (2, '阳台洗衣机', 'washer', 7, '小天鹅', 'TG100', '{"power":"off","status":"idle","mode":"standard","water_temp":"cold"}'),
  (2, '主卧门锁', 'door_lock', 5, '小米', 'E10', '{"power":"on","locked":true,"battery":100,"auto_lock":true}'),
  (2, '主卧摄像头', 'camera', 5, '小米', '云台2K', '{"power":"on","recording":false,"motion_detection":true,"night_vision":false}');
-- 5.2 环境感知 / 计量 / 安防 / 网络设备演示数据（中控指标绑定设备）
INSERT INTO devices (family_id, name, type, room_id, brand, model, status) VALUES
  (1, '客厅空气检测仪', 'air_monitor', 1, '青萍', 'AirMonitor Pro', '{"power":"on","pm25":35,"pm10":58,"co2":520,"hcho":0.04,"tvoc":0.2,"co":1.0,"air_quality":"优","battery":90}'),
  (1, '客厅温湿度传感器', 'temp_humidity_sensor', 1, '小米', 'WSDCGQ01LM', '{"online":true,"temperature":26.0,"humidity":55,"battery":95}'),
  (1, '卧室温湿度传感器', 'temp_humidity_sensor', 2, '小米', 'WSDCGQ01LM', '{"online":true,"temperature":25.5,"humidity":52,"battery":88}'),
  (1, '室外温湿度传感器', 'outdoor_sensor', 1, '绿米', 'Outhum V2', '{"online":true,"temperature":12.0,"humidity":60}'),
  (1, '室外气象站', 'weather_station', 1, '维特', 'WS100', '{"online":true,"weather":"晴","temperature":12.0,"humidity":60,"uv_index":3,"pressure":1013,"pm25":30,"air_quality":"优"}'),
  (1, '入户智能电表', 'electricity_meter', 1, '正泰', 'DDSU666', '{"online":true,"power_w":850,"voltage":220,"current":3.9,"daily_energy_kwh":8.6,"monthly_energy_kwh":210.4,"balance":186.5}'),
  (1, '客厅智能插座', 'smart_plug', 1, '小米', 'ZNCZ04CM', '{"power":"off","power_w":0,"energy_kwh":12.3,"voltage":220,"current":0}'),
  (1, '厨房智能水表', 'water_meter', 3, '宁水', 'LXSY', '{"online":true,"flow_rate":1.2,"daily_usage":0.35,"monthly_usage":8.6,"balance":32.5,"leak_alarm":false}'),
  (1, '厨房智能燃气表', 'gas_meter', 3, '金卡', 'G2.5', '{"online":true,"flow_rate":0.0,"monthly_usage":12.8,"balance":96.0,"gas_alarm":false}'),
  (1, '客厅门窗传感器', 'door_window_sensor', 1, '绿米', 'MCCGQ11LM', '{"online":true,"status":"closed","battery":90}'),
  (1, '客厅人体存在传感器', 'presence_sensor', 1, '海曼', 'FP2', '{"online":true,"presence":false,"battery":85}'),
  (1, '厨房水浸传感器', 'leak_sensor', 3, '小米', 'SJCGQ01LM', '{"online":true,"leak":false,"battery":80}'),
  (1, '厨房燃气传感器', 'gas_sensor', 3, '霍尼韦尔', 'GAS-01', '{"online":true,"gas_leak":false,"battery":80}'),
  (1, '卧室烟雾传感器', 'smoke_sensor', 2, '霍尼韦尔', 'SMK-01', '{"online":true,"smoke":false,"alarm":false,"battery":85}'),
  (1, '客厅智能路由器', 'router', 1, '华硕', 'RT-AX86U', '{"online":true,"internet_status":"online","wifi_ssid":"SmartHome-5G","signal_strength":85,"device_count":8,"bandwidth_mbps":300}'),
  (2, '阳台室外气象站', 'weather_station', 7, '维特', 'WS100', '{"online":true,"weather":"多云","temperature":13.0,"humidity":58,"uv_index":2,"pressure":1012,"pm25":28,"air_quality":"优"}'),
  (2, '卫生间温湿度传感器', 'temp_humidity_sensor', 6, '小米', 'WSDCGQ01LM', '{"online":true,"temperature":24.0,"humidity":68,"battery":92}'),
  (2, '阳台智能路由器', 'router', 7, 'TP-LINK', 'XDR6088', '{"online":true,"internet_status":"online","wifi_ssid":"HomeWiFi-6","signal_strength":80,"device_count":6,"bandwidth_mbps":500}'),
  (2, '主卧智能电表', 'electricity_meter', 5, '正泰', 'DDSU666', '{"online":true,"power_w":620,"voltage":220,"current":2.8,"daily_energy_kwh":6.2,"monthly_energy_kwh":168.9,"balance":210.0}'),
  (2, '主卧门窗传感器', 'door_window_sensor', 5, '绿米', 'MCCGQ11LM', '{"online":true,"status":"closed","battery":82}'),
  (2, '主卧烟雾传感器', 'smoke_sensor', 5, '霍尼韦尔', 'SMK-01', '{"online":true,"smoke":false,"alarm":false,"battery":78}');
-- 6. 创建场景
INSERT INTO scenes (family_id, name, description, actions) VALUES
  (1, '回家模式', '一键开启客厅设备',
   '{"actions":[{"device_type":"light","room_name":"客厅","attributes":{"power":"on","brightness":80}},{"device_type":"air_conditioner","room_name":"客厅","attributes":{"power":"on","temperature":26}},{"device_type":"curtain","room_name":"客厅","attributes":{"position":100}}]}'),
  (1, '睡眠模式', '关闭所有灯，空调调至睡眠温度',
   '{"actions":[{"device_type":"light","room_name":"客厅","attributes":{"power":"off"}},{"device_type":"light","room_name":"卧室","attributes":{"power":"off"}},{"device_type":"air_conditioner","room_name":"卧室","attributes":{"power":"on","temperature":25,"mode":"sleep"}}]}');

-- 7. 房主偏好画像示例
INSERT INTO user_preferences (user_id, preferences) VALUES
  (1, '{"preferred_temperature":{"summer":26,"winter":22},"sleep_schedule":{"bedtime":"23:00","wakeup":"07:00"},"interests":["音乐","阅读","电影"],"frequent_devices":["air_conditioner","light"],"interaction_style":"concise"}');
