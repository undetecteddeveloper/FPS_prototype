"""Mọi thông số chỉnh được của game nằm ở đây (một chỗ duy nhất). Đơn vị: mét, giây, độ.

Bảng debug (G6) sẽ đọc/ghi các dataclass này; module khác chỉ ĐỌC, không tự đặt số.
"""
from dataclasses import dataclass, field


@dataclass
class PlayerParams:
    # tốc độ mục tiêu theo trạng thái di chuyển (m/s)
    walk_speed: float = 4.5
    sprint_speed: float = 6.8
    crouch_speed: float = 2.2
    ads_speed_multiplier: float = 0.6     # nhân vào tốc độ khi ngắm (dùng từ G4)
    accel_ground: float = 45.0            # m/s^2
    accel_air: float = 6.0                # trên không gần như giữ nguyên đà
    gravity: float = 22.0
    jump_speed: float = 6.4               # độ cao nhảy = v^2 / 2g ≈ 0,93 m
    eye_height_stand: float = 1.62
    eye_height_crouch: float = 1.15
    eye_height_change_speed: float = 4.0  # m/s khi đứng lên / ngồi xuống
    fov: float = 80.0                     # FOV ngang của thế giới (CoD mặc định ~80)
    mouse_sensitivity: float = 45.0       # độ quay khi chuột đi hết CHIỀU CAO cửa sổ (không phụ thuộc độ phân giải)
    pitch_limit: float = 89.0
    moving_speed_threshold: float = 0.5   # trên mức này tính là "đang di chuyển"
    ads_look_multiplier: float = 0.7      # nhân vào độ nhạy chuột khi ngắm hẳn
    sprint_blocks_fire: bool = True       # bóp cò khi đang chạy: thôi chạy, súng hạ xuống rồi mới bắn (sprint-to-fire). False: bắn thẳng từ tư thế chạy
    land_dip_per_speed: float = 0.006     # m camera nhún xuống mỗi m/s tốc độ chạm đất (rơi 6,4 m/s nhún ~4 cm)
    land_dip_omega: float = 18.0          # rad/s
    land_dip_zeta: float = 0.5


@dataclass(frozen=True)
class Clip:
    """Một đoạn animation của glb. Khung tính theo 30 fps trên dòng thời gian chung của file."""
    anim: str
    start: int
    end: int       # khung CUỐI hợp lệ (khung N của clip có N khung bị bao về 0, nên không dùng N)
    swap: int = None   # khung băng mới vào chỗ (đo bằng tools/g5_reload_probe.py); chỉ clip reload có
    settle: int = None  # khung mà súng, băng đạn và bolt đã về chỗ: phần còn lại của clip chỉ là bàn tay xếp lại ngón (góc nhìn nạp tắt xong ở khung này)

    @property
    def duration(self) -> float:
        return (self.end - self.start) / 30.0

    @property
    def swap_time(self) -> float:
        """Giây (tính theo clip, tốc độ 1) kể từ đầu clip tới lúc thay băng; None nếu không có."""
        return None if self.swap is None else (self.swap - self.start) / 30.0


@dataclass
class RecoilData:
    """Recoil của CAMERA: mẫu theo từng phát, người chơi tự kéo chuột bù. Góc tính bằng độ."""
    pattern: tuple                        # ((lên, phải), ...) cho từng phát; quá cuối mẫu thì giữ bước cuối
    noise: float = 0.10                   # mỗi bước nhân (1 ± noise), ngẫu nhiên độc lập cho lên và phải
    pattern_reset_time: float = 0.35      # nghỉ bắn lâu hơn mức này thì phát kế quay về đầu mẫu
    kick_time: float = 0.025              # hằng số thời gian (s) làm mượt cú giật: camera không nhảy cục trong một khung
    recovery: float = 0.3                 # phần cú giật tự hồi về sau khi ngừng bắn (0 = không hồi, 1 = hồi hết)
    recovery_delay: float = 0.12          # ngừng bắn bao lâu thì bắt đầu hồi
    recovery_time: float = 0.18           # hằng số thời gian (s) của đường hồi


@dataclass
class AccuracyData:
    """Độ tản đạn: nửa góc hình nón (độ) = nền theo trạng thái + bloom cộng dồn."""
    stand: float = 2.0
    walk: float = 3.5
    sprint: float = 4.5
    air: float = 6.0                      # nhảy / rơi
    crouch_multiplier: float = 0.7        # nhân vào nền khi ngồi
    ads: float = 0.1                      # ngắm, đứng yên
    ads_move: float = 0.6                 # ngắm, đang đi
    bloom_per_shot: float = 0.25
    bloom_max: float = 4.0
    bloom_recovery: float = 6.0           # độ/giây
    bloom_recovery_delay: float = 0.15    # s sau phát cuối mới bắt đầu hồi; không có thì ở 750 phát/phút hồi (0,48° mỗi nhịp) triệt tiêu bloom (0,25° mỗi phát)
    ads_bloom_multiplier: float = 0.05    # khi ngắm hẳn, bloom chỉ còn ngần này tác dụng


@dataclass
class GunKickData:
    """Kick của SÚNG trên màn hình: lò xo giảm chấn, mỗi phát đẩy một xung. Nhỏ và nhanh hơn recoil camera.

    Các mảng là (x phải, y lên, z ra trước, pitch ngóc lên, yaw sang phải, roll nghiêng phải); mét và độ.
    `peak` = độ lệch đỉnh của MỘT phát đơn lẻ; `random` = biên độ ngẫu nhiên ± cộng vào mỗi phát."""
    omega: float = 38.0                   # rad/s, tần số riêng (chu kỳ ~0,17 s)
    zeta: float = 0.55                    # <1 thì súng nảy nhẹ trước khi yên
    peak: tuple = (0.0, 0.004, -0.022, 1.6, 0.0, 0.0)
    random: tuple = (0.002, 0.001, 0.003, 0.4, 0.4, 0.9)


@dataclass
class SwayData:
    """Súng đung đưa trên màn hình (không có clip Idle/Walk trong file nên toàn bộ bằng code). Mét và độ.
    Tư thế = (x phải, y lên, z ra trước, pitch ngóc lên, yaw phải, roll phải) như GunKick.peak."""
    # thở lúc đứng yên: đường Lissajous 1:2
    breath_freq: float = 0.28             # Hz
    breath_x: float = 0.0012
    breath_y: float = 0.0010
    breath_pitch: float = 0.10
    breath_yaw: float = 0.08
    # lag theo chuột: súng trễ ngược hướng quay, lò xo kéo về
    lag_gain: float = 0.35                # độ lệch súng mỗi độ góc nhìn quay
    lag_max: float = 4.0                  # độ
    lag_omega: float = 13.0               # rad/s
    lag_zeta: float = 0.7
    lag_roll: float = 0.4                 # độ nghiêng mỗi độ lệch yaw
    # bob theo bước chân (pha tăng theo quãng đường, nên nhịp đúng ở mọi tốc độ)
    bob_stride: float = 2.4               # m đi được mỗi chu kỳ chân trái-phải
    bob_x: float = 0.0045
    bob_y: float = 0.0060
    bob_pitch: float = 0.5
    bob_roll: float = 0.35
    bob_sprint_multiplier: float = 1.8
    bob_crouch_multiplier: float = 0.6
    bob_min_speed: float = 1.5            # m/s: dưới mức này biên độ bob nhỏ dần về 0
    bob_blend: float = 10.0               # 1/s: biên độ trượt về mức mới, dừng đột ngột không giật
    # tư thế chạy nước rút (hạ súng, chếch nòng); trộn theo player.sprint_amount
    sprint_pose: tuple = (0.02, -0.02, 0.02, -6.0, -18.0, 6.0)
    # quán tính theo chuyển động dọc của camera (nhảy, ngồi, đứng lên, rơi)
    vlag_gain: float = 0.05
    vlag_max: float = 0.03                # m
    jolt_omega: float = 14.0
    jolt_zeta: float = 0.6
    land_peak: tuple = (0.0, -0.012, -0.008, -1.5, 0.0, 0.0)   # độ lệch đỉnh khi chạm đất ở 6,4 m/s (tỉ lệ theo tốc độ)
    land_reference_speed: float = 6.4
    # ngắm: mọi thứ trên (thở, lag, bob, quán tính) nhân với số này khi ngắm hẳn
    ads_multiplier: float = 0.2


@dataclass
class ReloadData:
    """Rút súng (Draw) và nạp đạn (Reload / Reload_Empty). Thời gian lấy từ clip của file, nhân với `speed`."""
    speed: float = 1.0                    # nhân tốc độ clip reload: 1 = đúng clip gốc (3,6 s còn đạn / 3,8 s cạn); 1,5 thì ~2,4 s / 2,5 s
    draw_speed: float = 1.0
    sprint_cancels: bool = True           # chạy nước rút cắt reload (kiểu CoD); False: vẫn nạp tiếp, tư thế chạy chồng lên
    cancel_blend: float = 0.18            # s: súng trượt từ tư thế đang nạp về tư thế sẵn sàng khi huỷ
    bolt_lock_blend: float = 0.04         # s: bolt giật về sau (khoá nòng) khi bắn phát cuối của băng
    # Clip nạp được dựng cho góc nhìn rộng hơn: tay trái và băng đạn nằm dưới mép màn hình ở FOV hông (70). Khi nạp, FOV riêng của súng
    # mở rộng và súng nhích lên, trộn vào/ra trong `view_blend` giây (đo bằng ảnh chụp tools/g5_selftest.py)
    view_fov: float = 88.0
    view_pose: tuple = (-0.03, 0.04, 0.0, 0.0, 0.0, 0.0)   # (x phải, y lên, z ra trước, pitch lên, yaw phải, roll phải), m và độ
    view_blend: float = 0.25


@dataclass
class ViewLightData:
    """Ánh sáng riêng cho súng + tay (shader shaders/viewmodel.*). Không gian nhìn của camera súng: x phải, y lên, z về phía người xem."""
    sun_dir: tuple = (-0.40, 0.75, 0.52)  # hướng TỚI mặt trời: từ trên, hơi trái, hơi phía sau camera
    sun_color: tuple = (0.80, 0.77, 0.70)
    sky_color: tuple = (0.50, 0.54, 0.60)  # ánh sáng môi trường từ phía trên
    ground_color: tuple = (0.30, 0.29, 0.26)  # từ phía dưới (nảy từ mặt đất)
    specular: float = 0.30                # độ bóng kim loại (vệt sáng của mặt trời)
    rim: float = 0.22                     # viền sáng ở mép vật thể


@dataclass
class FlashData:
    """Tia lửa đầu nòng (vẽ trong cảnh súng): ngôi sao hướng về camera + hai tấm chéo dọc nòng + đèn điểm chiếu sáng súng và tay.
    Mỗi phát quay ngẫu nhiên và đổi cỡ chút ít; sống `life` giây rồi tắt dần (ở 750 phát/phút các phát chồng nhau sẽ thành chớp liên tục)."""
    life: float = 0.055                   # s
    size: float = 0.21                    # m: đường kính ngôi sao (trong cảnh súng, miệng nòng cách mắt 0,73 m)
    size_jitter: float = 0.25             # +- tỉ lệ cỡ ngẫu nhiên mỗi phát
    length: float = 0.20                  # m: dài hai tấm chéo dọc nòng
    width: float = 0.07                   # m: rộng hai tấm chéo
    forward: float = 0.025                # m: nhích ra trước miệng nòng cho khỏi chìm vào bộ giảm giật
    color: tuple = (1.0, 0.86, 0.52)
    ads_scale: float = 0.35               # khi ngắm hẳn, tia lửa chỉ còn ngần này cỡ (không che đường ngắm)
    light_color: tuple = (1.0, 0.62, 0.28)
    light_power: float = 1.5              # nhân vào màu đèn lúc sáng nhất
    light_attenuation: tuple = (1.0, 0.0, 40.0)   # hằng, tuyến tính, bậc hai theo mét: sáng tới ~0,3 m quanh nòng


@dataclass
class TracerData:
    """Tracer: vệt sáng đi theo viên đạn thật (cùng vị trí, cùng độ rơi), xuất phát từ miệng nòng rồi hội tụ về đường đạn từ mắt."""
    every: int = 3                        # cứ mấy viên có một tracer (1 = mọi viên); viên đầu tiên của loạt luôn có
    burst_reset: float = 0.30             # ngừng bắn lâu hơn mức này (s) thì loạt mới: đếm lại từ viên đầu
    max_range: float = 600.0              # m: đạn đi quá xa thì vệt dừng theo (đạn bay lên trời vẫn sống 3 s, không cần vệt đuổi theo)
    length: float = 7.0                   # m: vệt dài (đạn 500 m/s đi ~8 m mỗi khung 60 FPS, ngắn hơn thì thành chấm rời)
    width: float = 0.05                   # m: rộng ở gần
    min_pixels: float = 2.2               # rộng tối thiểu trên màn hình (ở xa tracer mảnh dưới 1 điểm ảnh sẽ nhấp nháy)
    glow_pixels: float = 20.0             # đầu vệt có một chấm sáng hướng về camera, cỡ này trên màn hình (đạn bay xa dọc hướng nhìn thì vệt co lại thành chấm)
    glow_color: tuple = (1.0, 0.62, 0.18)
    blend_distance: float = 18.0          # m: đi bao xa thì vệt đã hết lệch khỏi đường đạn thật (lệch = miệng nòng so với mắt)
    head_color: tuple = (1.0, 0.86, 0.45)   # trộn cộng lên nền sáng nên cần màu bão hoà, trắng sẽ chìm vào mặt đường và bầu trời
    tail_color: tuple = (1.0, 0.36, 0.06)
    intensity: float = 1.0
    pool: int = 16                        # số vệt tối đa cùng lúc


# Mẫu recoil 30 phát của M4: mỗi phát (lên, phải) độ. Hay lên, trôi phải, lắc nhẹ sang trái giữa băng.
M4_PATTERN = (
    (0.42, 0.04), (0.40, 0.08), (0.38, 0.11), (0.37, 0.14), (0.36, 0.16),
    (0.35, 0.17), (0.34, 0.18), (0.33, 0.17), (0.32, 0.15), (0.31, 0.12),
    (0.30, 0.08), (0.30, 0.04), (0.29, 0.00), (0.29, -0.04), (0.28, -0.08),
    (0.28, -0.10), (0.27, -0.08), (0.27, -0.04), (0.26, 0.02), (0.26, 0.08),
    (0.26, 0.14), (0.25, 0.18), (0.25, 0.19), (0.25, 0.17), (0.24, 0.14),
    (0.24, 0.09), (0.24, 0.04), (0.23, 0.00), (0.23, 0.05), (0.23, 0.10),
)


@dataclass
class GunData:
    """Dữ liệu một khẩu súng. Thêm súng thứ hai = thêm một GunData, không sửa logic."""
    name: str
    glb: str
    credit: str
    clips: dict
    recoil: RecoilData                    # mỗi súng có mẫu recoil riêng (xem M4 bên dưới)
    accuracy: AccuracyData = field(default_factory=AccuracyData)
    kick: GunKickData = field(default_factory=GunKickData)
    sway: SwayData = field(default_factory=SwayData)
    reload: ReloadData = field(default_factory=ReloadData)
    view_light: ViewLightData = field(default_factory=ViewLightData)
    flash: FlashData = field(default_factory=FlashData)
    tracer: TracerData = field(default_factory=TracerData)
    # ngắm (ADS)
    ads_time: float = 0.25                # s để vào / ra
    ads_fov: float = 65.0                 # FOV ngang của thế giới khi ngắm hẳn
    ads_sights: tuple = None              # (tâm vòng ngắm sau, đỉnh cột ngắm trước) trong hệ camera lúc nghỉ, KHÔNG tính hip_offset
    ads_eye_relief: float = 0.18          # m: vòng ngắm sau cách mắt bao xa khi ngắm (xa hơn: vòng nhỏ hơn, che ít hơn)
    muzzle: tuple = None                  # miệng nòng trong hệ camera lúc nghỉ như ads_sights (đo bằng tools/g5_muzzle_align.py)
    # chạy nước rút
    sprint_in_time: float = 0.20          # s để hạ súng vào tư thế chạy
    sprint_out_time: float = 0.25         # s để đưa súng lên lại; trong lúc này chưa bắn được (sprint-to-fire)
    # âm thanh phát súng
    shot_sound: str = None                # đường dẫn từ gốc dự án; dựng bằng tools/prep_sound.py từ file gốc trong sounds/source
    shot_volume: float = 0.8
    shot_pool: int = 8                    # số bản phát luân phiên: độ dài tiếng (0,5 s) / nhịp bắn (0,08 s) + 1, để tiếng sau không cắt tiếng trước
    shot_pitch_variation: float = 0.03    # ± tỉ lệ đổi cao độ ngẫu nhiên mỗi phát cho đỡ "máy"; 0 = tắt
    eye_joint: str = 'FPS_Camera_j_01'    # khớp mà góc nhìn gốc của animation đặt camera vào
    model_scale: float = 0.01             # file tính bằng cm
    view_fov: float = 70.0                # FOV ngang riêng của camera vẽ súng (>75 thì lộ cẳng tay trái bị xoắn da)
    hip_offset: tuple = (0.0, 0.0, 0.0)   # dịch thêm viewmodel so với góc nhìn gốc (x phải, y lên, z ra trước)
    # bắn
    rpm: float = 750.0                    # phát/phút
    magazine: int = 30
    reserve: int = 150
    full_auto: bool = True                # chế độ lúc vào game (phím B đổi tự động / bắn đơn)
    # đạn bay có độ rơi: rơi ~0,11 m ở 75 m và ~0,44 m ở 150 m
    muzzle_velocity: float = 500.0        # m/s
    bullet_gravity: float = 9.81          # m/s^2
    bullet_lifetime: float = 3.0          # s; quá thì bỏ đạn (bay ra ngoài làn)


M4 = GunData(
    name='M4',
    glb='guns/m4_-_fps_weapon_animations_pack_v.1.glb',
    credit='M4: BarcodeGames (CC-BY 4.0)',
    clips={
        # swap = khung băng mới vào chỗ (còn đạn: băng cũ rút ra rồi băng mới ấn vào lúc 2,0 s; cạn: 2,03 s, bolt nhả ở khung 190)
        'reload': Clip('Reload', 1, 110, swap=61, settle=88),
        'reload_empty': Clip('Reload_Empty', 111, 224, swap=172, settle=206),
        'fire': Clip('Fire', 226, 249),
        'holster': Clip('Holster', 251, 268),
        'draw': Clip('Draw', 269, 299),
    },
    recoil=RecoilData(pattern=M4_PATTERN),
    # đo bằng đỉnh mô hình (tools/g4_ads_align.py): tâm vòng ngắm sau và đỉnh cột ngắm trước
    ads_sights=((0.0678, -0.0074, 0.1556), (0.0678, -0.0069, 0.5622)),
    muzzle=(0.0677, -0.0752, 0.7326),
    shot_sound='sounds/m4_shot.wav',
)


@dataclass
class FeedbackParams:
    """Phản hồi khi đạn trúng: hit marker, nháy màu bia, lỗ đạn."""
    hit_marker_duration: float = 0.15
    target_flash_duration: float = 0.12
    last_hit_display_time: float = 2.0    # hiện khoảng cách bia vừa trúng bao lâu
    hole_base_size: float = 0.05          # m; lỗ đạn thật chỉ 5,56 mm, phóng to để nhìn thấy
    hole_size_per_meter: float = 0.002    # lỗ càng xa càng to thêm (150 m: ~0,35 m)
    max_holes: int = 200                  # quá thì tái dùng lỗ cũ nhất


@dataclass
class LookData:
    """Giao diện hình ảnh của thế giới (shader shaders/world.*) và lớp phủ màn hình. Hướng tính trong thế giới (y lên, z ra trước)."""
    sun_dir: tuple = (0.40, 0.72, -0.56)  # hướng TỚI mặt trời: từ trên, từ phía sau lưng người chơi (mặt bia hướng về người chơi được chiếu sáng)
    sun_color: tuple = (0.68, 0.62, 0.48)
    sky_color: tuple = (0.66, 0.72, 0.80)     # ánh sáng môi trường từ trời
    ground_color: tuple = (0.46, 0.43, 0.38)  # từ đất nảy lên
    fog_color: tuple = (0.75, 0.84, 0.87)     # màu chân trời (khớp ảnh trời)
    fog_density: float = 0.0032               # exp: ~46% ở 200 m, ~85% ở 600 m
    detail_strength: float = 0.55             # độ sâu của nhiễu trên mặt đất (0 = tắt)
    vignette: float = 0.30                    # độ tối ở góc màn hình (0 = tắt)


@dataclass
class GameParams:
    player: PlayerParams = field(default_factory=PlayerParams)
    gun: GunData = field(default_factory=lambda: M4)
    feedback: FeedbackParams = field(default_factory=FeedbackParams)
    look: LookData = field(default_factory=LookData)
