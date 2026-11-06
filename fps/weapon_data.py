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
    eye_height_stand: float = 1.68        # camera đội đầu: cao hơn mắt ~6 cm
    eye_height_crouch: float = 1.20
    eye_height_change_speed: float = 4.0  # m/s khi đứng lên / ngồi xuống
    fov: float = 96.0                     # FOV ngang của ảnh TRƯỚC khi qua ống kính; ống kính mắt cá phóng giữa khung ~1,25 lần nên giữa khung trông như ~83 độ, rìa thấy rộng hơn
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
    """Giật sinh ngẫu nhiên từng phát (kiểu Bodycam), không có mẫu cố định. Góc tính bằng độ, là TỔNG một phát; `camera_share` đi vào góc nhìn
    (người chơi kéo chuột bù), phần còn lại làm SÚNG trôi khỏi tâm (core/freeaim.py). Đạn bay theo nòng nên cả hai đều đổi điểm trúng."""
    up: float = 0.72                      # lên mỗi phát
    up_noise: float = 0.20                # ± ngẫu nhiên của phần lên
    right_bias: float = 0.05              # xu hướng lệch phải trung bình mỗi phát
    right_noise: float = 0.30             # ± ngẫu nhiên từng phát của phần ngang
    right_walk: float = 0.07              # xu hướng ngang đi ngẫu nhiên mỗi phát: mỗi loạt trôi một kiểu
    right_walk_max: float = 0.30          # trần của xu hướng ngang trôi
    up_scale: float = 1.0                 # nhân vào phần lên (bảng debug: 2 = gấp đôi, 0 = không giật lên)
    right_scale: float = 1.0              # nhân vào phần ngang
    camera_share: float = 0.30            # phần cú giật đi vào camera; 0,7 còn lại làm súng trôi
    ads_scale: float = 0.75               # ngắm (báng tì vai): cú giật nhân ngần này
    crouch_scale: float = 0.85            # ngồi: nhân ngần này
    burst_reset_time: float = 0.35        # nghỉ bắn lâu hơn mức này thì xu hướng ngang của loạt làm lại từ đầu
    kick_time: float = 0.025              # hằng số thời gian (s) làm mượt cú giật: camera không nhảy cục trong một khung
    recovery: float = 0.3                 # phần cú giật của camera tự hồi về sau khi ngừng bắn (0 = không hồi, 1 = hồi hết)
    recovery_delay: float = 0.12          # ngừng bắn bao lâu thì bắt đầu hồi
    recovery_time: float = 0.18           # hằng số thời gian (s) của đường hồi


@dataclass
class AccuracyData:
    """Độ tản CƠ KHÍ của súng + đạn (nửa góc hình nón, độ). Sự thiếu chính xác khi đi / chạy / giật nay đến từ NÒNG thật sự lệch đi (đạn bay theo nòng),
    nên hình nón theo trạng thái đã bỏ: mọi trạng thái cùng ~2 MOA. Các trường vẫn giữ để chỉnh được trên bảng F1 (và selftest đo độ tản)."""
    stand: float = 0.03
    walk: float = 0.03
    sprint: float = 0.03
    air: float = 0.03                     # nhảy / rơi
    crouch_multiplier: float = 1.0        # nhân vào nền khi ngồi
    ads: float = 0.03                     # ngắm, đứng yên
    ads_move: float = 0.03                # ngắm, đang đi
    bloom_per_shot: float = 0.0
    bloom_max: float = 4.0
    bloom_recovery: float = 6.0           # độ/giây
    bloom_recovery_delay: float = 0.15    # s sau phát cuối mới bắt đầu hồi
    ads_bloom_multiplier: float = 0.05    # khi ngắm hẳn, bloom chỉ còn ngần này tác dụng


@dataclass
class GunKickData:
    """Kick của SÚNG trên màn hình: lò xo giảm chấn, mỗi phát đẩy một xung. Nhỏ và nhanh hơn recoil camera.

    Các mảng là (x phải, y lên, z ra trước, pitch ngóc lên, yaw sang phải, roll nghiêng phải); mét và độ.
    `peak` = độ lệch đỉnh của MỘT phát đơn lẻ; `random` = biên độ ngẫu nhiên ± cộng vào mỗi phát."""
    omega: float = 38.0                   # rad/s, tần số riêng (chu kỳ ~0,17 s)
    zeta: float = 0.55                    # <1 thì súng nảy nhẹ trước khi yên
    peak: tuple = (0.0, 0.004, 0.0, 0.7, 0.0, 0.0)      # z = 0: đẩy lùi do lò xo riêng bên dưới lo (lò xo này nhanh, đỉnh một phát không dồn lên khi bắn liên thanh)
    random: tuple = (0.002, 0.001, 0.0, 0.25, 0.25, 1.3)
    # ĐẨY LÙI (MW2): súng bị đẩy về phía mắt (z âm) rồi trượt về. Lò xo RIÊNG, chậm hơn lò xo trên (chu kỳ dài hơn nhịp bắn 0,08 s) nên các
    # phát dồn lên: ở 750 phát/phút một phát đơn lùi 3,6 cm, cả băng dồn tới ~6 cm rồi bão hoà (khi ngắm nhân back_ads_scale) (đo: tools/g3_selftest.py), ngừng bắn thì ~0,3 s về chỗ.
    back_peak: float = -0.030             # m: đỉnh của MỘT phát đơn lẻ; âm = lùi về phía mắt
    back_random: float = 0.003            # m: ± ngẫu nhiên mỗi phát
    back_omega: float = 18.0              # rad/s (chu kỳ ~0,35 s)
    back_zeta: float = 0.7
    back_ads_scale: float = 1.15          # khi ngắm hẳn đẩy lùi nhân ngần này (1,3 = lùi NHIỀU hơn hông 30%; chỉ là hình ảnh của súng; camera và hướng đạn không đổi)
    back_x_ratio: float = 0.3             # nhích ngang theo đẩy lùi (m ngang mỗi m lùi; súng lùi thì nhích vào giữa màn hình, khỏi trượt ra rìa phải). Chỉ lúc hông, ngắm thì 0


@dataclass
class SwayData:
    """Súng đung đưa trên màn hình (không có clip Idle/Walk trong file nên toàn bộ bằng code). Mét và độ.
    Tư thế = (x phải, y lên, z ra trước, pitch ngóc lên, yaw phải, roll phải) như GunKick.peak."""
    # thở lúc đứng yên: đường Lissajous 1:2
    breath_freq: float = 0.28             # Hz
    breath_x: float = 0.0022
    breath_y: float = 0.0020
    breath_pitch: float = 0.22
    breath_yaw: float = 0.18
    # lag theo chuột (core/sway.py MouseLag): súng bám góc nhìn qua hệ bậc hai, trễ theo VẬN TỐC quay; dừng chuột thì đuổi kịp, vượt, lắc về
    lag_gain: float = 0.055               # s: xoay đều ve (độ/s) thì súng lệch lag_gain * ve độ (100 độ/s -> ~5 độ), vùng tuyến tính
    lag_max: float = 12.0                 # độ: mức tiệm cận của lệch ổn định khi xoay rất mạnh (nén mềm tanh, không kẹp phẳng); đỉnh cú flick ~ngần này
    lag_omega: float = 9.5                # rad/s: lớn = súng bắt kịp nhanh (không đổi biên độ)
    lag_zeta: float = 0.62                # giảm chấn: nhỏ = nảy nhiều (0,6 ~ quá đà 13%, 0,45 ~ 25%); 0,99 = không quá đà
    lag_roll: float = 0.9                 # độ nghiêng mỗi độ lệch yaw
    lag_pitch_scale: float = 0.8          # trễ dọc (ngẩng/cúi) so với trễ ngang
    lag_shift: float = 0.0022             # m dịch ngang/dọc mỗi độ lệch (cộng thêm cho chuyển động cung do xoay quanh mắt)
    lag_deadzone: float = 12.0            # độ/s: dưới mức này (xoay chậm lúc ngắm kỹ) súng gần như đứng yên
    lag_smooth: float = 0.02              # s: làm mượt tốc độ quay đo từ chuột (chuột bắn số đếm rời rạc)
    lag_follow: float = 0.0               # 0 = trễ hoàn toàn theo tốc độ quay; 1 = súng bám sát, chỉ còn nảy khi đổi tốc độ
    # bob theo bước chân (pha tăng theo quãng đường, nên nhịp đúng ở mọi tốc độ)
    bob_stride: float = 2.4               # m đi được mỗi chu kỳ chân trái-phải (khi bob_rate = 1)
    bob_rate: float = 0.56                # nhịp bob so với bob_stride khi đi/ngồi đi (0,56: tăng 40% so với 0,4; ~4,3 m mỗi chu kỳ)
    bob_sprint_rate: float = 0.483        # nhịp bob khi chạy nước rút (0,3 -> 0,42 tăng 40%, rồi +15% nữa: ~2,8 bước/s)
    bob_x: float = 0.0070
    bob_y: float = 0.0100
    bob_pitch: float = 1.0
    bob_roll: float = 1.1
    bob_sprint_multiplier: float = 1.8
    bob_crouch_multiplier: float = 0.6
    bob_min_speed: float = 1.5            # m/s: dưới mức này biên độ bob nhỏ dần về 0
    bob_blend: float = 10.0               # 1/s: biên độ trượt về mức mới, dừng đột ngột không giật
    # tư thế cầm súng lúc thường (hông): thấp và gần giữa khung, không ngắm thẳng. Cộng thêm vào hip_offset; trộn về 0 khi ngắm
    rest_pose: tuple = (-0.050, -0.112, 0.020, 0.0, 0.0, -3.0)
    # tư thế chạy nước rút (hạ súng, chếch nòng); trộn theo player.sprint_amount
    sprint_pose: tuple = (-0.01, -0.012, 0.02, -7.0, -16.0, 10.0)
    # quán tính theo chuyển động dọc của camera (nhảy, ngồi, đứng lên, rơi)
    vlag_gain: float = 0.05
    vlag_max: float = 0.03                # m
    jolt_omega: float = 14.0
    jolt_zeta: float = 0.6
    land_peak: tuple = (0.0, -0.012, -0.008, -1.5, 0.0, 0.0)   # độ lệch đỉnh khi chạm đất ở 6,4 m/s (tỉ lệ theo tốc độ)
    land_reference_speed: float = 6.4
    # ngắm: mọi thứ trên (thở, lag, bob, quán tính) nhân với số này khi ngắm hẳn
    ads_multiplier: float = 0.45


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
    view_fov: float = 92.0
    # (x phải, y lên, z ra trước, pitch lên, yaw phải, roll phải), m và độ. y 0,125 -> 0,105 khi thêm liếc súng (HeadCamData.glance_*): đầu cúi 18 độ
    # và súng đi theo thì băng lúc thay (đo trên mô hình: dưới mắt 27-32 độ, ~30 cm trước) nằm ~12-16 độ dưới giữa khung, thân súng ngay dưới giữa
    view_pose: tuple = (0.07, 0.105, -0.02, 0.0, 0.0, 2.5)
    view_blend: float = 0.25


@dataclass
class ViewLightData:
    """Vật liệu súng + tay (shaders/viewmodel.*). KHÔNG có đèn riêng: súng nhận đúng các đèn trần, bóng, ánh nền và tia lửa của thế giới."""
    specular: float = 0.55                # độ bóng kim loại của thân súng (vệt sáng của đèn trần)
    gloss: float = 26.0                   # độ tập trung của vệt sáng trên thân súng
    env: float = 0.35                     # phản chiếu mờ môi trường (nhân theo ánh nền tại chỗ: chỗ tối thì mất)
    normal_strength: float = 1.0          # độ nổi của normal map
    albedo: float = 1.25                  # nhân màu texture: texture của súng rất tối, qua đường tông gắt thì mất hết chi tiết
    sleeve_color: tuple = (0.060, 0.062, 0.058)   # màu tay áo phủ lên phần da cẳng tay (asset là da trần, có vân xoắn)


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
    world_power: float = 3.5              # độ sáng tia lửa lên tường / sàn (0 = chỉ chiếu súng)
    world_falloff: float = 0.22           # 1 / (1 + falloff * d^2): ~2 m còn một nửa


@dataclass
class TracerData:
    """Tracer: vệt sáng đi theo viên đạn thật (cùng vị trí, cùng độ rơi), xuất phát từ miệng nòng rồi hội tụ về đường đạn từ mắt."""
    every: int = 2                        # cứ mấy viên có một tracer (1 = mọi viên); viên đầu tiên của loạt luôn có
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


def _m4_reload_beats() -> dict:
    """Mốc rung khi nạp, theo khung của clip (đo bằng tools/g5_reload_probe.py): băng cũ bung ra, băng mới vào chỗ (= Clip.swap), bolt nhả.
    Khung tính theo dòng thời gian chung của file; Handling.frame đã nhân ReloadData.speed nên mốc đúng ở mọi tốc độ nạp."""
    return {
        'reload': ((27, 'mag_out'), (61, 'seat')),
        'reload_empty': ((137, 'mag_out'), (172, 'seat'), (190, 'bolt')),
    }


def _beat_peaks() -> dict:
    # độ lệch đỉnh của camera cho MỘT mốc: (x phải, y lên, z ra trước, pitch ngóc lên, yaw phải, roll phải), mét và độ. Nhẹ: tối đa ~0,2 độ, ~2 mm
    return {
        'mag_out': (0.0, -0.0004, 0.0, -0.06, 0.03, 0.10),
        'seat': (0.0, -0.0010, -0.0012, -0.20, 0.05, 0.22),
        'bolt': (0.0, 0.0005, -0.0020, 0.15, 0.06, 0.18),
    }


@dataclass
class ShakeData:
    """Camera shake: rung thuần hình ảnh (không đổi hướng đạn), xem core/shake.py. Mét và độ."""
    seed: int = 7
    # bắn: MỖI PHÁT một cú giật camera (xung lò xo), độ mạnh và hướng ngẫu nhiên; sấy thì "nóng" dần, giật mạnh hơn và run tay
    # độ lệch đỉnh một phát (lò xo đang yên, độ mạnh 1) = fire_bias + fire_spread x số ngẫu nhiên có dấu trong [-1, 1], từng trục (x, y, z, pitch, yaw, roll)
    fire_bias: tuple = (0.0, 0.0, -0.003, 1.0, 0.0, 0.0)              # phần cố định: lùi 3 mm, ngóc 1 độ
    fire_spread: tuple = (0.0015, 0.0015, 0.0015, 0.30, 0.55, 2.0)    # phần ngẫu nhiên ±: roll tới 2 độ là kênh thấy rõ nhất (recoil camera không có roll)
    direction_shape: float = 0.6          # số mũ của phần ngẫu nhiên (< 1: ít phát gần 0, yaw / roll thường rõ một phía)
    strength_var: float = 0.4             # độ mạnh của phát = 1 ± ngần này (0,6 .. 1,4)
    strength_shape: float = 0.7           # < 1: nhiều phát mạnh hẳn / nhẹ hẳn hơn là phát vừa
    fire_omega: float = 38.0              # rad/s: lò xo của cú giật; đỉnh sau ~0,03 s, còn ~25% sau một nhịp 0,08 s nên loạt dồn lên vừa phải
    fire_zeta: float = 0.45               # nảy ngược một chút rồi yên trong ~0,15 s
    fire_scale: float = 1.0               # nhân MỌI rung khi bắn (cú giật + run tay, camera + súng, cả khi ngắm); rung khi nạp không bị nhân
    # sấy: độ nóng 0..1 của loạt
    heat_shots: float = 25.0              # số phát liên tục để nóng hẳn (mỗi phát cộng 1 / ngần này)
    heat_hold: float = 0.12               # s: ngừng bắn lâu hơn mức này mới nguội (> nhịp 0,08 s nên sấy không nguội giữa chừng)
    heat_cool: float = 3.0                # /s: nguội từ 1 về 0 trong 0,33 s (sau heat_hold)
    heat_boost: float = 1.2               # cú giật nhân 1 + ngần này x độ nóng. Đỉnh cả băng / đỉnh 30 phát lẻ (trung bình 10 seed): pitch 1,9, roll 2,0
                                          # (1,0 chỉ cho ~1,8 vì đỉnh của 30 phát lẻ đã là phát ngẫu nhiên mạnh nhất)
    tremor_amp: tuple = (0.0006, 0.0006, 0.0004, 0.25, 0.30, 0.60)   # run tay nền khi nóng hẳn (x, y, z, pitch, yaw, roll), nhân độ nóng
    tremor_freq: float = 22.0             # Hz: run tay nhanh hơn hẳn nhịp bắn (12,5 Hz)
    # nạp: xung lò xo tại các mốc clip, không rung liên tục
    reload_beats: dict = field(default_factory=_m4_reload_beats)    # khoá clip -> ((khung, loại mốc), ...)
    beat_peaks: dict = field(default_factory=_beat_peaks)          # loại mốc -> độ lệch đỉnh
    beat_omega: float = 42.0              # rad/s (chu kỳ ~0,15 s)
    beat_zeta: float = 0.45               # nảy 1-2 lần rồi yên trong ~0,15 s
    # khi ngắm hẳn rung giảm còn ngần này
    ads_multiplier: float = 0.5
    # súng trên màn hình đi theo thế giới (đảo dấu) ngần này và trễ `gun_delay` giây: súng rung ít hơn và hơi trễ hơn thế giới thì tự nhiên hơn
    gun_follow: float = 0.6
    gun_delay: float = 0.02


@dataclass
class FreeAimData:
    """Súng không về một điểm cố định trên màn hình (core/freeaim.py). Đạn bay theo nòng. Độ và mét."""
    barrel_aim: bool = True               # True: đạn theo nòng + chuột điều khiển súng trước; False: chuột quay thẳng màn hình, đạn ra giữa (selftest đo độ rơi / khi cần so sánh)
    # VÙNG TỰ DO (core/freeaim.py FreeLook): chuột di chuyển SÚNG trong hình elip quanh giữa màn hình; ra tới mép thì màn hình mới quay theo.
    # Số do tôi chọn: nguồn công khai không có số của Bodycam (bản mod Garry's Mod dùng 45 / 30 độ, quá rộng với màn hình này)
    zone_yaw: float = 15.0                # độ: nửa bề ngang vùng tự do
    zone_pitch: float = 9.0               # độ: nửa bề dọc
    zone_soft: float = 0.70               # từ phần này của bán kính vùng trở ra, màn hình bắt đầu quay dần (không chạm mép đánh cộp)
    zone_ads: float = 0.20                # khi ngắm hẳn vùng còn ngần này: thước ngắm về gần giữa, màn hình tự quay bù nên điểm ngắm không nhảy
    zone_sprint: float = 0.35             # khi chạy nước rút
    zone_reload: float = 0.50             # khi nạp đạn
    zone_blend: float = 0.14              # s: vùng co / giãn mượt
    recenter_idle: float = 0.22           # /s: đứng yên thì đầu từ từ quay theo súng (súng giữ nguyên hướng trong thế giới, chỉ khung hình đuổi theo)
    recenter_move: float = 1.0            # /s: khi đang đi thì thân người quay theo súng nhanh hơn
    hand_omega: float = 15.0              # rad/s: tay đưa súng theo chuột, không dính cứng vào chuột
    hand_zeta: float = 0.85
    offset_roll: float = 0.22             # độ nghiêng súng mỗi độ lệch ngang
    offset_shift: float = 0.0016          # m súng dịch trên khung mỗi độ lệch (thêm vào cung xoay quanh mắt)
    drift_omega: float = 7.0              # rad/s: súng trôi do giật về chỗ bằng lò xo này (nhỏ = lâu về, các phát dồn nhiều)
    drift_zeta: float = 0.95
    drift_max: float = 9.0                # độ: độ trôi tiệm cận mức này khi bắn rất lâu (nén mềm)
    rest_yaw: float = 0.8                 # độ: sau mỗi cú xoay / loạt đạn, tư thế nghỉ ngẫu nhiên trong khoảng ± này (không về đúng một toạ độ)
    rest_pitch: float = 0.6
    rest_roll: float = 2.2
    rest_pos: float = 0.007               # m
    rest_time: float = 0.55               # s: thời gian trượt sang tư thế nghỉ mới
    rest_turn_threshold: float = 60.0     # độ/s: xoay nhanh hơn mức này thì chọn tư thế nghỉ mới khi dừng
    idle_yaw: float = 0.32                # độ: trôi chậm lúc đứng yên (tay không cứng như giá đỡ)
    idle_pitch: float = 0.26
    idle_roll: float = 0.45
    idle_freq: float = 0.22               # Hz
    ads_scale: float = 0.30               # khi ngắm hẳn: độ trôi nghỉ + trôi chậm còn ngần này (phần giật vẫn giữ nguyên)
    stress_per_shot: float = 0.045        # căng thẳng cộng mỗi phát (0..1): bắn nhiều thì tay run
    stress_decay: float = 0.10            # /s
    tremor_freq: float = 8.5              # Hz
    tremor_angle: float = 0.45            # độ: run tay ở mức căng thẳng 1
    tremor_pos: float = 0.0016            # m
    tremor_reload: float = 2.2            # lúc nạp đạn run tay nhân ngần này (clip nạp chỉ có hai biến thể nên run tay làm mỗi lần nạp một khác)


@dataclass
class HeadCamData:
    """Camera đội đầu (core/headcam.py): CHỈ HÌNH ẢNH, không đổi tia ngắm. Độ và mét."""
    seed: int = 23
    turn_roll: float = 0.016              # độ nghiêng mỗi độ/s xoay ngang (đầu nghiêng theo cú xoay)
    turn_roll_max: float = 4.5
    strafe_roll: float = 0.55             # độ nghiêng mỗi m/s đi ngang
    move_pitch: float = 0.20              # độ cúi mỗi m/s đi tới
    turn_yaw_lag: float = 0.008           # s: khung hình trễ nhẹ sau cú xoay (thân đến sau)
    body_omega: float = 7.0               # rad/s: lò xo thân người: nhỏ = thân đến trễ
    body_zeta: float = 0.75
    # bước chân khi ĐI (cùng pha Sway.phase, tức cùng nhịp tiếng bước chân). Kiểu quay bodycam: thấy rõ nhưng không chóng mặt
    step_y: float = 0.020                 # m: nhún (đáy -2 cm đúng lúc chân chạm đất, đỉnh thấp hơn vì sóng đáy nhọn)
    step_x: float = 0.010                 # m: lắc ngang theo chân trụ
    step_roll: float = 1.1                # độ: nghiêng trái phải theo nhịp chân
    step_pitch: float = 0.7               # độ: gật theo bước
    step_yaw: float = 0.4                 # độ: đầu xoay theo vai
    step_sharp: float = 0.6               # 0 = nhún hình sin; 1 = đáy nhọn như cú dậm
    step_crouch: float = 0.55             # ngồi đi: nhân biên độ bước + rung tay
    step_min_speed: float = 1.5           # m/s: dưới mức này biên độ nhỏ dần về 0
    step_blend: float = 8.0               # 1/s: biên độ trượt về mức mới
    # chạy nước rút: bộ biên độ riêng (trộn mượt với bộ đi theo `sprint_blend`)
    sprint_y: float = 0.030
    sprint_x: float = 0.016
    sprint_roll: float = 2.6              # độ: nghiêng mạnh trái phải theo nhịp chân
    sprint_pitch: float = 1.3
    sprint_yaw: float = 0.9
    sprint_lean: float = 1.5              # độ: chúi tới thêm (cộng với move_pitch theo tốc độ)
    sprint_blend: float = 5.0             # 1/s
    # rung tay / rung máy tần số cao: nhiễu mượt, tăng theo tốc độ, mạnh nhất khi chạy nước rút
    jitter_angle: float = 0.5             # độ (pitch; yaw x0,8; roll x1,2) khi chạy nước rút
    jitter_pos: float = 0.0015            # m
    jitter_walk: float = 0.3              # đi: còn ngần này
    jitter_freq: float = 12.0             # Hz khi chạy
    jitter_freq_walk: float = 7.0         # Hz khi đi
    idle_pitch: float = 0.22              # độ: đầu trôi chậm lúc đứng yên
    idle_yaw: float = 0.22
    idle_roll: float = 0.32
    idle_y: float = 0.0025                # m: thở
    idle_freq: float = 0.17               # Hz
    # nhảy / rơi / chạm đất: xung vào lò xo nhanh `jolt_*` (zeta < 0,5 nên nảy lại một nhịp); đỉnh tính ở tốc độ chuẩn, tỉ lệ theo tốc độ
    jump_pitch: float = 1.6               # độ: ngóc lên lúc bật nhảy
    jump_y: float = 0.008                 # m
    jump_roll: float = 0.6                # độ: ± ngẫu nhiên
    air_sway: float = 0.5                 # độ: lắc chậm khi đang trên không
    air_freq: float = 1.4                 # Hz
    land_pitch: float = 4.0               # độ: dằn xuống khi chạm đất ở tốc độ chuẩn
    land_y: float = 0.025                 # m: dằn xuống (cộng với cú nhún thật của Player._dip)
    land_roll: float = 1.4                # độ: ± nghiêng ngẫu nhiên (yaw ± 30% số này)
    land_reference_speed: float = 6.4     # m/s rơi ứng với đỉnh trên (= tốc độ bật nhảy)
    land_max: float = 1.8                 # rơi cao hơn thì tối đa ngần này lần
    jolt_omega: float = 14.0              # rad/s
    jolt_zeta: float = 0.40
    ads_multiplier: float = 0.5           # ngắm hẳn: chuyển động đầu còn ngần này (không áp cho liếc súng)
    gun_follow: float = 0.55              # súng đi theo chuyển động đầu (đảo dấu) ngần này: tay nối với thân chứ không dính vào ống kính
    # LIẾC SÚNG KHI NẠP: đầu cúi nhìn băng đạn rồi ngẩng lên, theo thời gian clip (chỉ hình ảnh; chuột vẫn quay, tia ngắm không đổi).
    # 18 độ cúi + súng đi theo 1 đưa băng đạn lúc thay (dưới mắt ~30 độ) về giữa-dưới khung (đo bằng mô hình, xem ReloadData.view_pose)
    glance_pitch: float = 18.0            # độ: cúi xuống
    glance_yaw: float = 6.0               # độ: quay về phía súng (súng lệch phải)
    glance_roll: float = 3.0              # độ: nghiêng theo
    glance_y: float = -0.015              # m: đầu cúi thì mắt hạ xuống
    glance_z: float = 0.015               # m: và nhô ra trước
    glance_in_delay: float = 0.06         # s sau khi bấm nạp mới bắt đầu cúi
    glance_in_time: float = 0.32          # s để cúi hẳn
    glance_out_lead: float = 0.25         # s TRƯỚC Clip.settle thì bắt đầu ngẩng (cùng lúc góc nhìn nạp tắt dần)
    glance_out_time: float = 0.38         # s để ngẩng hẳn: về 0 trước khi súng sẵn sàng bắn ~0,5 s
    glance_cancel_time: float = 0.2       # s: huỷ nạp thì ngẩng về trong ngần này
    glance_drift: float = 1.0             # độ: mắt trôi nhẹ khi đang nhìn
    glance_drift_freq: float = 0.5        # Hz
    glance_seat_nod: float = 1.2          # độ: gật nhỏ lúc băng vào chỗ (Clip.swap)
    glance_follow: float = 1.0            # súng đi theo phần liếc (đảo dấu): 1 = súng đứng yên theo thân, trên màn hình đi lên giữa khung


@dataclass
class GunData:
    """Dữ liệu một khẩu súng. Thêm súng thứ hai = thêm một GunData, không sửa logic."""
    name: str
    glb: str
    credit: str
    clips: dict
    recoil: RecoilData = field(default_factory=RecoilData)
    accuracy: AccuracyData = field(default_factory=AccuracyData)
    kick: GunKickData = field(default_factory=GunKickData)
    sway: SwayData = field(default_factory=SwayData)
    reload: ReloadData = field(default_factory=ReloadData)
    view_light: ViewLightData = field(default_factory=ViewLightData)
    flash: FlashData = field(default_factory=FlashData)
    tracer: TracerData = field(default_factory=TracerData)
    shake: ShakeData = field(default_factory=ShakeData)
    free_aim: FreeAimData = field(default_factory=FreeAimData)
    head: HeadCamData = field(default_factory=HeadCamData)
    # ngắm (ADS)
    ads_time: float = 0.19                # s để vào / ra
    ads_fov: float = 84.5                 # FOV ngang của thế giới khi ngắm hẳn: kèm ống kính bớt méo (LensData.fisheye_ads), giữa khung phóng ~13%
    ads_view_fov: float = 74.0            # FOV của camera vẽ súng khi ngắm hẳn: thước ngắm đủ to để dùng (đạn vẫn đi đúng chỗ đầu ruồi đang chỉ, xem freeaim.barrel_view_dir)
    ads_sights: tuple = None              # (tâm vòng ngắm sau, đỉnh cột ngắm trước) trong hệ camera lúc nghỉ, KHÔNG tính hip_offset
    ads_eye_relief: float = 0.18          # m: vòng ngắm sau cách mắt bao xa khi ngắm (xa hơn: vòng nhỏ hơn, che ít hơn)
    muzzle: tuple = None                  # miệng nòng trong hệ camera lúc nghỉ như ads_sights (đo bằng tools/g5_muzzle_align.py)
    # chạy nước rút
    sprint_in_time: float = 0.20          # s để hạ súng vào tư thế chạy
    sprint_out_time: float = 0.25         # s để đưa súng lên lại; trong lúc này chưa bắn được (sprint-to-fire)
    # âm thanh phát súng
    shot_sound: tuple = ()                # đường dẫn từ gốc dự án (nhiều biến thể, phát luân phiên); dựng bằng tools/prep_elevenlabs.py từ sounds/source/elevenlabs
    shot_volume: float = 0.8
    shot_pool: int = 8                    # số bản phát luân phiên: độ dài tiếng (0,5 s) / nhịp bắn (0,08 s) + 1, để tiếng sau không cắt tiếng trước
    shot_pitch_variation: float = 0.03    # ± tỉ lệ đổi cao độ ngẫu nhiên mỗi phát cho đỡ "máy"; 0 = tắt
    eye_joint: str = 'FPS_Camera_j_01'    # khớp mà góc nhìn gốc của animation đặt camera vào
    model_scale: float = 0.01             # file tính bằng cm
    view_fov: float = 92.0                # FOV ngang riêng của camera vẽ súng: gần FOV thế giới để súng đúng tỉ lệ thật so với phòng
    hip_offset: tuple = (0.0, 0.0, 0.0)   # dịch thêm viewmodel so với góc nhìn gốc (x phải, y lên, z ra trước)
    # bắn
    rpm: float = 750.0                    # phát/phút
    magazine: int = 30
    reserve: int = 600
    full_auto: bool = True                # chế độ lúc vào game (phím B đổi tự động / bắn đơn)
    # đạn bay có độ rơi: rơi ~0,11 m ở 75 m và ~0,44 m ở 150 m
    muzzle_velocity: float = 500.0        # m/s
    bullet_gravity: float = 9.81          # m/s^2
    bullet_lifetime: float = 3.0          # s; quá thì bỏ đạn (bay ra ngoài làn)


M4 = GunData(
    name='M4',
    glb='guns/m4_-_fps_weapon_animations_pack_v.1.glb',
    credit='M4: BarcodeGames (CC BY 4.0)',
    clips={
        # swap = khung băng mới vào chỗ (còn đạn: băng cũ rút ra rồi băng mới ấn vào lúc 2,0 s; cạn: 2,03 s, bolt nhả ở khung 190)
        'reload': Clip('Reload', 1, 110, swap=61, settle=88),
        'reload_empty': Clip('Reload_Empty', 111, 224, swap=172, settle=206),
        'fire': Clip('Fire', 226, 249),
        'holster': Clip('Holster', 251, 268),
        'draw': Clip('Draw', 269, 299),
    },
    # đo bằng đỉnh mô hình (tools/g4_ads_align.py): tâm vòng ngắm sau và đỉnh cột ngắm trước
    ads_sights=((0.0678, -0.0074, 0.1556), (0.0678, -0.0069, 0.5622)),
    muzzle=(0.0677, -0.0752, 0.7326),
    shot_sound=('sounds/el_shot_0.wav', 'sounds/el_shot_1.wav', 'sounds/el_shot_2.wav'),
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
    """Giao diện hình ảnh của thế giới (shader shaders/world.*) và lớp phủ màn hình. Hướng tính trong thế giới (y lên, z ra trước).
    Phòng tập kín (kích thước ở core/room.RoomLayout), không có trời/mặt trời: nguồn sáng là một dãy bóng đèn treo trần dọc giữa làn."""
    # đèn trần: một dãy cách đều dọc làn; vị trí đèn i = (lamp_x, lamp_y, lamp_z0 + i * lamp_spacing)
    lamp_x: float = 0.0
    lamp_y: float = 4.6                       # bóng đèn (trần ở 5,5 m; chóa đèn treo bằng ống)
    lamp_z0: float = -15.0                    # giữa hai dầm trần (dầm ở -10, 0, 10, ...)
    lamp_spacing: float = 10.0
    lamp_count: int = 23                      # tới z = 205
    lamp_color: tuple = (1.0, 0.93, 0.80)     # trung tính hơi vàng (đèn cao áp cũ, ~4000 K)
    lamp_intensity: float = 6.0              # độ rọi = intensity / (1 + (d / lamp_ref)^2), nhân cửa sổ tắt dần tới lamp_radius
    lamp_ref: float = 3.6                     # m: ở khoảng cách này độ rọi còn một nửa
    lamp_radius: float = 15.0                 # m: ngoài bán kính này đèn không chiếu. <= 1,5 khoảng cách đèn thì mỗi điểm ảnh chỉ xét 3 đèn (nhanh hơn hẳn 5 đèn)
    lamp_emissive: float = 9.0                # độ sáng của bóng đèn / lòng chóa (tự phát sáng, không nhận đèn)
    lamp_cone: float = 25.0                   # độ: trong nón này (tính từ phương thẳng đứng) chóa đèn rọi đủ sáng
    lamp_cone_outer: float = 55.0             # độ: ra ngoài nón này chỉ còn lamp_side (tạo quầng sáng dưới mỗi đèn)
    lamp_side: float = 0.115                  # phần ánh sáng lọt ra ngang mép chóa; trên mép chóa thì 0
    lamp_halo: float = 0.55                  # độ sáng quầng mờ quanh bóng đèn (thẻ cộng sáng, 0 = tắt)
    ambient_up: tuple = (0.016, 0.017, 0.018)    # ánh sáng hắt chung lên mặt hướng lên (sàn): rất thấp, chỗ khuất đèn gần như đen
    ambient_down: tuple = (0.022, 0.021, 0.019)  # lên mặt hướng xuống (trần)
    bounce_color: tuple = (0.040, 0.036, 0.030)  # ánh dội từ vũng sáng trên sàn lên tường/trần gần đó, mỗi đơn vị độ sáng đèn (đèn tắt hoặc không có đèn gần thì 0)
    exposure: float = 1.0                     # nhân vào phơi sáng tự động (LensData); đường tông ACES dùng chung cho thế giới và súng
    shadows: object = True                    # True: bóng thật (bản đồ độ sâu 5 mặt cho từng đèn); 'fake': vệt tối giả dưới bia/cột + AO; False: không bóng
    shadow_face_size: int = 256               # điểm ảnh mỗi mặt của mỗi đèn (23 đèn x 5 mặt xếp chung một kết cấu)
    shadow_bias: tuple = (0.02, 0.012)        # m: đẩy điểm ra theo pháp tuyến = a + b * khoảng cách tới đèn (chống "acne")
    shadow_soft_distance: float = 18.0        # m: gần hơn mức này lấy 4 mẫu bóng cho mềm, xa hơn 1 mẫu (ở xa không thấy khác, rẻ hơn 4 lần)
    shadow_max_distance: float = 400.0        # m: xa hơn mức này không lấy mẫu bóng (hạ xuống khi cần thêm FPS: cuối làn mất bóng trước)
    mover_shadow_hz: float = 6.0              # bóng thật của bia chạy: mỗi bia được vẽ lại bóng bấy nhiêu lần/giây (lần lượt từng bia, mỗi lần chỉ vài đèn gần)
    mover_shadow_reach: float = 0.60          # chỉ vẽ lại đèn cách bia dọc z trong phần này của lamp_radius (ngoài đó ánh sáng gần tắt, bóng cũ không lộ)
    fog_color: tuple = (0.004, 0.004, 0.0035)  # bụi trong phòng: bụi không tự sáng nên xa dần chìm vào tối
    fog_density: float = 0.0025               # exp: ~22% ở 100 m, ~39% ở 200 m
    detail_strength: float = 0.9              # độ sâu của nhiễu trên mặt đất (0 = tắt)


@dataclass
class LensData:
    """Ống kính camera đội đầu (shaders/lens.frag, toán ở core/lens.py + core/exposure.py), vẽ SAU khi đã ghép thế giới và súng."""
    fisheye: float = 0.25                 # độ méo mắt cá: 0 = ảnh phẳng; giữa khung phóng (1 + fisheye) lần
    fisheye_ads: float = 0.16             # khi ngắm hẳn méo bớt
    chroma: float = 0.012                 # viền màu: chênh độ méo giữa kênh đỏ và lam, tăng dần ra rìa
    smear: float = 0.030                  # nhoè ở rìa khi đứng yên (tỉ lệ khung hình)
    smear_motion: float = 0.00022         # nhoè thêm mỗi độ/s xoay
    smear_start: float = 0.50             # bán kính bắt đầu nhoè (0 giữa .. 1 mép ngang)
    rolling_shutter: float = 0.00011      # màn trập cuộn: hàng trên/dưới lệch ngang theo tốc độ xoay (tỉ lệ khung mỗi độ/s)
    vignette_start: float = 0.78          # bán kính bắt đầu tối (đơn vị 1 = mép ngang)
    vignette_end: float = 1.14            # bán kính tối hẳn; góc khung đen như ảnh chụp Bodycam
    fringe: float = 0.55                  # vầng cam ở ranh giới tối góc (ánh sáng lọt mép ống kính)
    noise: float = 0.030                  # nhiễu cảm biến, mạnh hơn ở vùng tối
    bloom: float = 0.45                   # vùng sáng loé ra xung quanh; 0 = tắt (rẻ hơn)
    bloom_threshold: float = 0.72         # từ độ sáng này mới loé
    contrast: float = 1.10                # > 1: tối tối hơn, sáng sáng hơn
    saturation: float = 0.70              # 1 = giữ màu, 0 = xám
    tint: tuple = (1.0, 1.0, 0.93)        # ánh vàng bệnh của camera giá rẻ
    auto_exposure: float = 0.55           # 0 = phơi sáng cố định, 1 = bù hoàn toàn theo độ sáng tại chỗ
    exposure_key: float = 0.70            # độ sáng tại chỗ ứng với phơi sáng 1
    exposure_min: float = 0.55
    exposure_max: float = 2.2
    exposure_up_time: float = 1.4         # s: từ sáng vào tối mắt camera mở dần (chậm)
    exposure_down_time: float = 0.35      # s: từ tối ra sáng khép nhanh hơn (loá rồi mới về)
    lamp_glare: float = 0.9               # nhìn thẳng vào đèn thì phơi sáng tụt: phần còn lại của khung tối đi


@dataclass(frozen=True)
class SoundCue:
    """Một tiếng gắn vào khung của clip: phát khi clip chạy tới `frame` (khung tuyệt đối trên dòng thời gian của glb, như Clip.swap)."""
    frame: int
    sound: str                            # tên nhóm trong sounds/foley (tools/prep_foley.py): file <sound>_<số>.wav
    volume: float = 1.0                   # nhân vào AudioData.reload_volume


# Mốc âm thanh của M4, đo bằng tools/g5_reload_probe.py (khoảng cách băng / bolt / chốt so với tư thế sẵn sàng theo từng khung).
M4_SOUND_CUES = {
    # Reload (1..110): chốt băng bấm ở 26, băng rời chỗ từ 27 (cách 6 cm, rồi 15 cm ở 29, 30 cm ở 31), băng mới trượt vào 49..60, vào chỗ 61 (= Clip.swap),
    # bolt/chốt đập nhẹ ở 74..76, băng lún thêm cho chắc ở 83
    # Tiếng của người dùng (AudioData.sound_files), ba cú va của file gốc: (1) chốt băng, (2) băng trượt vào rồi vào chỗ, (3) bolt.
    # NẠP THƯỜNG (còn đạn trong nòng) chỉ có HAI cú đầu: chốt băng 26, băng trượt vào 57..60 (rất nhỏ), băng vào chỗ 61. Không còn tiếng tổng hợp cũ.
    'reload': (SoundCue(26, 'mag_release', 0.9), SoundCue(57, 'mag_in', 0.7), SoundCue(61, 'mag_seat', 1.0)),
    # Reload_Empty (111..224): bolt đang khoá sau. Băng rời từ 137, băng mới vào chỗ 172 (= Clip.swap), BOLT NHẢ về trước ở 190 (bolt 7,0 -> 4,4 -> 3,0 cm),
    # bolt về hẳn 197..199, băng lún thêm ở 201
    # NẠP CẠN: chạy hết cả ba cú (thêm bolt nhả về trước ở 190).
    'reload_empty': (SoundCue(136, 'mag_release', 0.9), SoundCue(168, 'mag_in', 0.7), SoundCue(172, 'mag_seat', 1.0), SoundCue(190, 'bolt_release', 1.0)),
    # Draw (269..299): súng bắt đầu nhấc ở 270, nhấc nhanh nhất 272..280, gần yên từ 284, nằm hẳn ở ~287
    'draw': (SoundCue(271, 'draw_a', 0.8), SoundCue(285, 'draw_b', 0.6)),
}


@dataclass
class AudioData:
    """Foley: tiếng kim loại khi nạp / rút súng (theo khung animation) và bước chân trên gạch (theo quãng đường). Tiếng dựng bằng tools/prep_foley.py.
    Âm lượng nhỏ hơn tiếng súng (GunData.shot_volume 0,8) để không át tiếng bắn."""
    folder: str = 'sounds/foley'
    pool: int = 2                         # số bản phát luân phiên cho mỗi file: tiếng sau không cắt đuôi tiếng trước
    # tên logic của tiếng -> nhóm file thật trong folder (<nhóm>_<số>.wav). Mặc định dùng tiếng tạo bằng ElevenLabs (tools/prep_elevenlabs.py từ sounds/source/elevenlabs).
    # Muốn quay về tiếng người dùng cung cấp trước đây: đổi el_* thành user_* (mag_release, mag_in, mag_seat, bolt, step). Xoá một dòng là về tiếng tổng hợp của tên đó (tools/prep_foley.py).
    sound_files: dict = field(default_factory=lambda: {
        'mag_release': 'el_mag_release', 'mag_in': 'el_mag_in', 'mag_seat': 'el_mag_seat',
        'bolt_tick': 'el_bolt', 'bolt_release': 'el_bolt',
        'draw_a': 'el_draw_a', 'draw_b': 'el_draw_b', 'settle': 'el_settle',
        'step_walk': 'el_step', 'step_run': 'el_step', 'land': 'el_land', 'jump': 'el_jump',
        'dry': 'el_dry', 'hit_target': 'el_hit_target', 'hit_hard': 'el_hit_hard', 'breath': 'el_breath'})
    # nhân vào cao độ khi phát một tên logic (chạy dùng chung file với đi, cao hơn một chút)
    pitch_scale: dict = field(default_factory=lambda: {'step_run': 1.06})
    # nạp / rút súng
    cues: dict = field(default_factory=lambda: dict(M4_SOUND_CUES))   # khoá clip (GunData.clips) -> các SoundCue; thời điểm thật = (frame - clip.start) / 30 / tốc độ clip
    reload_volume: float = 0.5
    cancel_sound: str = 'settle'          # tay trượt về tư thế sẵn sàng khi huỷ nạp (chỉ khi đã có ít nhất một tiếng của lần nạp đó)
    cancel_delay: float = 0.06            # s sau lúc huỷ
    cancel_volume: float = 0.6
    # bước chân: MỖI LẦN súng chạm điểm thấp nhất của bob (Sway.phase đi qua step_bob_phase và step_bob_phase + pi, tức hai bước mỗi chu kỳ bob) thì phát một tiếng.
    # Nhịp bước vì thế khớp nhịp sway súng ở mọi tốc độ (bob_rate / bob_sprint_rate / bob_stride của SwayData). Các sải bên dưới chỉ dùng khi KHÔNG có sway (test, dự phòng).
    step_bob_phase: float = 2.356         # rad (= 3 pi / 4): pha bob lúc súng thấp nhất = chân chạm đất (y bob = sin(2 pha) nhỏ nhất)
    step_stride_walk: float = 0.75        # m mỗi bước
    step_stride_sprint: float = 1.0
    step_stride_crouch: float = 0.5
    step_start_phase: float = 0.5         # 0..1: bước đầu tiên sau khi đứng yên đến sớm (nửa sải)
    step_min_speed: float = 0.5           # m/s: chậm hơn thì không tính là đi
    step_volume: float = 0.30
    step_sprint_multiplier: float = 1.25
    step_crouch_multiplier: float = 0.35
    step_pitch_variation: float = 0.05    # +- tỉ lệ cao độ ngẫu nhiên
    step_volume_variation: float = 0.10   # +- tỉ lệ âm lượng ngẫu nhiên
    foot_pitch: float = 0.02              # chân trái thấp hơn, chân phải cao hơn ngần này (luân phiên)
    foot_pan: float = 0.15                # lệch kênh trái / phải (-1..1)
    # chạm đất / nhảy
    land_min_speed: float = 2.0           # m/s: rơi chậm hơn thì chỉ là bước chân
    land_reference_speed: float = 6.4     # tốc độ rơi cho âm lượng chuẩn (nhảy tại chỗ rồi hạ xuống)
    land_volume: float = 0.50
    land_gain_range: tuple = (0.45, 1.3)  # nhân âm lượng theo tốc độ rơi / tốc độ chuẩn, kẹp trong khoảng này
    jump_volume: float = 0.25
    # game không có HUD nên tiếng đạn trúng là phản hồi chính. Tiếng đi từ chỗ trúng về tai: tới muộn theo tốc độ âm thanh, nhỏ dần theo khoảng cách
    hit_target_volume: float = 0.75
    hit_hard_volume: float = 0.50
    hit_reference_distance: float = 45.0  # m: xa ngần này thì âm lượng còn một nửa
    hit_pitch_variation: float = 0.05     # +- tỉ lệ cao độ ngẫu nhiên
    speed_of_sound: float = 343.0         # m/s
    dry_volume: float = 0.55              # bóp cò khi hết sạch đạn
    # tiếng thở khi đứng yên (core/breath.py): mỗi chu kỳ thở của sway (SwayData.breath_freq) một hơi, cùng đồng hồ với sự nhấp nhô của súng
    breath_volume: float = 0.35
    breath_min_idle: float = 0.5          # bob (đi / chạy) chiếm quá nửa thì không bắt đầu hơi thở mới
    breath_ads_scale: float = 0.5         # ngắm hẳn: nhỏ còn ngần này (nín thở)


@dataclass
class GameParams:
    player: PlayerParams = field(default_factory=PlayerParams)
    gun: GunData = field(default_factory=lambda: M4)
    feedback: FeedbackParams = field(default_factory=FeedbackParams)
    look: LookData = field(default_factory=LookData)
    audio: AudioData = field(default_factory=AudioData)
    lens: LensData = field(default_factory=LensData)
