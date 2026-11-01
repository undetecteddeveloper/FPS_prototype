"""Danh sách thanh trượt của bảng debug (F1): nhóm, mục, nhãn tiếng Việt, chú thích ngắn, khoảng giá trị.

Thuần dữ liệu (không import ursina). `fps/core/params.py` đọc bảng này rồi dò các dataclass của `weapon_data.py` (introspection) để
biết kiểu và giá trị mặc định của từng trường, nên con số mặc định chỉ nằm ở `weapon_data.py`. Ở đây chỉ có cái KHÔNG suy ra được:
tên hiển thị, chú thích, khoảng kéo hợp lý, trường nâng cao, trường cần khởi động lại.

Quy ước cờ (chuỗi ký tự): 'A' = nâng cao (ẩn cho tới khi bấm "Nâng cao"), 'R' = cần khởi động lại mới có hiệu lực.
Thiếu lo/hi/step thì `params.py` tự suy từ giá trị mặc định (0 .. 3 lần mặc định). Mọi trường số / bật-tắt của `GameParams` phải nằm trong
một nhóm HOẶC trong `EXCLUDED` kèm lý do (test_params.py kiểm đủ), nên thêm trường mới vào weapon_data mà quên đây thì pytest báo.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Meta:
    label: str
    hint: str = ''
    lo: float = None
    hi: float = None
    step: float = None
    flags: str = ''
    choices: tuple = None      # ((giá trị, chữ hiện), ...) cho trường chọn một trong vài

    @property
    def advanced(self) -> bool:
        return 'A' in self.flags

    @property
    def restart(self) -> bool:
        return 'R' in self.flags


def p(label, hint='', lo=None, hi=None, step=None, flags='') -> Meta:
    return Meta(label, hint, lo, hi, step, flags)


# --- cụm trường lặp lại ---
POSE_AXES = ('sang phải', 'lên', 'ra trước', 'ngóc nòng', 'xoay nòng phải', 'nghiêng phải')
POSE_HINTS = ('mét; âm = sang trái', 'mét; âm = xuống', 'mét; âm = lùi về phía người', 'độ; dương = nòng ngóc lên',
              'độ; dương = nòng quay sang phải', 'độ; dương = nghiêng sang phải')


def pose(prefix: str, ranges: tuple, adv: str = '', hints: tuple = POSE_HINTS) -> tuple:
    """6 thành phần của một tư thế (x phải, y lên, z ra trước, pitch ngóc lên, yaw phải, roll phải). `ranges` = 6 bộ (lo, hi, step);
    `adv` = chuỗi 6 ký tự, 'A' ở thành phần nâng cao (bất kỳ ký tự khác = thường)."""
    adv = adv.ljust(6)
    return tuple(p(f'{prefix}: {axis}', hint, lo, hi, step, 'A' if a == 'A' else '')
                 for axis, hint, (lo, hi, step), a in zip(POSE_AXES, hints, ranges, adv))


def rgb(prefix: str, hi: float, step: float, hint: str = 'thành phần màu, 0 = tối, lớn = sáng') -> tuple:
    return tuple(p(f'{prefix}: {c}', hint, 0.0, hi, step, 'A') for c in ('đỏ', 'lục', 'lam'))


MOVE = (-0.05, 0.05, 0.0005)
ANGLE = (-5.0, 5.0, 0.1)

META = {
    # ---------------- Bắn ----------------
    'gun.rpm': p('Tốc độ bắn', 'phát mỗi phút; M4 ngoài đời khoảng 750', 120, 1500, 10),
    'gun.muzzle_velocity': p('Tốc độ đạn', 'm/s; chậm thì đạn tới bia muộn và rơi nhiều', 100, 1200, 10),
    'gun.bullet_gravity': p('Độ rơi của đạn', 'm/s²; 0 = bay thẳng, 9,81 = như thật', 0, 30, 0.1),
    'gun.bullet_lifetime': p('Đạn sống tối đa', 'giây; quá hạn thì đạn biến mất', 0.5, 10, 0.5, 'A'),
    'gun.magazine': p('Đạn trong băng', 'viên mỗi băng', 5, 100, 1, 'R'),
    'gun.reserve': p('Đạn dự trữ', 'tổng số viên mang theo ngoài băng', 0, 600, 10, 'R'),
    'feedback.hit_marker_duration': p('Hit marker hiện', 'giây sau mỗi phát trúng bia', 0.03, 0.6, 0.01),
    'feedback.last_hit_display_time': p('Hiện khoảng cách', 'giây hiện số mét của bia vừa trúng', 0.5, 6, 0.1),
    'feedback.hole_base_size': p('Cỡ lỗ đạn', 'mét; lỗ thật nhỏ hơn nhiều, phóng to cho dễ thấy', 0.01, 0.2, 0.005),
    'feedback.hole_size_per_meter': p('Lỗ to thêm theo xa', 'mét cộng thêm cho mỗi mét khoảng cách', 0, 0.01, 0.0005, 'A'),

    # ---------------- Giật ----------------
    'gun.recoil.up_scale': p('Mức giật lên', '1 = đúng mẫu M4; 2 = gấp đôi; 0 = không giật', 0, 3, 0.05),
    'gun.recoil.right_scale': p('Mức lệch phải', '1 = đúng mẫu; 0 = lên thẳng; âm = lệch trái', -2, 3, 0.05),
    'gun.recoil.noise': p('Độ ngẫu nhiên', '± tỉ lệ mỗi phát; 0 = lần nào cũng y hệt', 0, 0.5, 0.01),
    'gun.recoil.pattern_reset_time': p('Nghỉ để mẫu làm lại', 'giây ngừng bắn rồi phát kế quay về đầu mẫu', 0.05, 1.5, 0.05),
    'gun.recoil.recovery': p('Tự hồi sau loạt', 'phần cú giật tự về lại; 0 = không hồi, 1 = hồi hết', 0, 1, 0.05),
    'gun.recoil.recovery_delay': p('Chờ rồi mới hồi', 'giây sau phát cuối', 0, 0.6, 0.01),
    'gun.recoil.recovery_time': p('Tốc độ hồi', 'giây; nhỏ = hồi nhanh', 0.02, 1, 0.01, 'A'),
    'gun.recoil.kick_time': p('Độ mượt cú giật', 'giây; lớn = camera giật mềm hơn', 0, 0.15, 0.005, 'A'),
    'gun.kick.omega': p('Độ cứng lò xo súng', 'lớn = súng nảy nhanh và gọn', 10, 80, 1, 'A'),
    'gun.kick.zeta': p('Độ nảy của súng', 'nhỏ = nảy nhiều, gần 1 = dừng ngay', 0.1, 0.99, 0.01),
    'gun.kick.back_peak': p('Đẩy lùi mỗi phát', 'mét; âm = lùi về phía người; bắn liên thanh dồn thêm ~1,7 lần', -0.1, 0.0, 0.002),
    'gun.kick.back_x_ratio': p('Đẩy lùi kéo súng vào giữa', 'mét ngang mỗi mét lùi (lúc hông); 0 = lùi thẳng', 0, 1, 0.05, 'A'),
    'gun.kick.back_random': p('Đẩy lùi ngẫu nhiên', 'mét; ± thêm vào mỗi phát', 0, 0.02, 0.0005, 'A'),
    'gun.kick.back_omega': p('Độ cứng lò xo đẩy lùi', 'nhỏ = lùi chậm, dồn nhiều khi bắn liên thanh và lâu về chỗ', 8, 60, 1, 'A'),
    'gun.kick.back_zeta': p('Độ nảy của đẩy lùi', 'nhỏ = nảy nhiều, gần 1 = trượt về không nảy', 0.1, 0.99, 0.01, 'A'),
    'gun.kick.back_ads_scale': p('Đẩy lùi khi ngắm', 'nhân vào đẩy lùi lúc ngắm hẳn; 0,5 = còn một nửa', 0, 1.5, 0.05),
    'gun.kick.peak': pose('Kick mỗi phát', ((-0.02, 0.02, 0.0005), (-0.03, 0.03, 0.0005), (-0.1, 0.1, 0.001), (-6, 6, 0.1),
                                           (-4, 4, 0.1), (-4, 4, 0.1)), adv='A   AA'),
    'gun.kick.random': pose('Kick ngẫu nhiên', ((0, 0.01, 0.0005), (0, 0.01, 0.0005), (0, 0.02, 0.0005), (0, 2, 0.05),
                                                (0, 2, 0.05), (0, 3, 0.05)), adv='AAAAAA',
                            hints=('mét; ± thêm vào mỗi phát',) * 3 + ('độ; ± thêm vào mỗi phát',) * 3),

    # ---------------- Độ tản ----------------
    'gun.accuracy.stand': p('Đứng yên', 'độ; nửa góc hình nón đạn rải ra', 0, 10, 0.05),
    'gun.accuracy.walk': p('Đi bộ', 'độ', 0, 12, 0.05),
    'gun.accuracy.sprint': p('Chạy nước rút', 'độ (chỉ có tác dụng khi tắt "bóp cò thì thôi chạy")', 0, 12, 0.05),
    'gun.accuracy.air': p('Nhảy / rơi', 'độ', 0, 12, 0.05),
    'gun.accuracy.crouch_multiplier': p('Hệ số khi ngồi', 'nhân vào độ tản; 0,7 = chính xác hơn 30%', 0.1, 1.5, 0.05),
    'gun.accuracy.ads': p('Ngắm, đứng yên', 'độ', 0, 3, 0.05),
    'gun.accuracy.ads_move': p('Ngắm, đang đi', 'độ', 0, 6, 0.05),
    'gun.accuracy.bloom_per_shot': p('Bloom cộng mỗi phát', 'độ tản thêm sau mỗi phát', 0, 1, 0.01),
    'gun.accuracy.bloom_max': p('Bloom tối đa', 'độ; trần của phần tản thêm', 0, 10, 0.1),
    'gun.accuracy.bloom_recovery': p('Tốc độ hồi bloom', 'độ mỗi giây', 0.5, 30, 0.5),
    'gun.accuracy.bloom_recovery_delay': p('Chờ trước khi hồi', 'giây sau phát cuối mới bắt đầu hồi', 0, 0.6, 0.01),
    'gun.accuracy.ads_bloom_multiplier': p('Bloom còn lại khi ngắm', 'nhân vào bloom lúc ngắm hẳn', 0, 1, 0.01),

    # ---------------- Ngắm ----------------
    'gun.ads_time': p('Thời gian vào ngắm', 'giây để đưa súng lên mắt (và ngược lại)', 0.05, 0.8, 0.01),
    'gun.ads_eye_relief': p('Mắt cách điểm ngắm', 'mét; xa hơn thì vòng ngắm nhỏ lại, ít che hình', 0.05, 0.4, 0.005),
    'player.fov': p('Tầm nhìn lúc bắn hông', 'độ (FOV ngang); lớn = thấy rộng hơn', 60, 110, 1),
    'gun.ads_fov': p('Tầm nhìn khi ngắm', 'độ; nhỏ hơn lúc hông = phóng to', 30, 90, 1),
    'gun.view_fov': p('Tầm nhìn của súng', 'độ; cỡ súng trên màn hình, trên 75 lộ cẳng tay xoắn da', 50, 90, 1),
    'player.ads_speed_multiplier': p('Tốc độ đi khi ngắm', 'nhân vào tốc độ đi', 0.1, 1.2, 0.05),
    'player.ads_look_multiplier': p('Độ nhạy chuột khi ngắm', 'nhân vào độ nhạy chuột', 0.2, 1.5, 0.05),

    # ---------------- Sway & bob ----------------
    'gun.sway.breath_freq': p('Nhịp thở', 'Hz', 0.05, 1, 0.01),
    'gun.sway.breath_x': p('Thở: lắc ngang', 'mét', 0, 0.006, 0.0001),
    'gun.sway.breath_y': p('Thở: nhấp dọc', 'mét', 0, 0.006, 0.0001),
    'gun.sway.breath_pitch': p('Thở: gật nòng', 'độ', 0, 0.6, 0.01),
    'gun.sway.breath_yaw': p('Thở: xoay nòng', 'độ', 0, 0.6, 0.01),
    'gun.sway.lag_gain': p('Độ trễ theo chuột', 'giây: súng lệch (gain x tốc độ quay độ/s) độ; 0 = không trễ', 0, 0.15, 0.005),
    'gun.sway.lag_max': p('Trễ tối đa', 'độ; xoay rất mạnh thì tiệm cận mức này (không kẹp phẳng)', 0, 20, 0.5),
    'gun.sway.lag_omega': p('Độ cứng lò xo trễ', 'lớn = súng bắt kịp nhanh (không đổi biên độ)', 3, 40, 0.5, 'A'),
    'gun.sway.lag_zeta': p('Độ nảy khi bắt kịp', 'nhỏ = vượt quá nhiều rồi lắc về (0,6 ~ 13%)', 0.1, 0.99, 0.01, 'A'),
    'gun.sway.lag_roll': p('Nghiêng khi quay chuột', 'độ nghiêng mỗi độ lệch', 0, 2, 0.05),
    'gun.sway.lag_pitch_scale': p('Trễ dọc so với ngang', 'ngẩng/cúi chuột: nhân độ trễ', 0, 1.5, 0.05, 'A'),
    'gun.sway.lag_shift': p('Súng dịch khi quay chuột', 'mét mỗi độ lệch, cộng với cung xoay quanh mắt', 0, 0.006, 0.0001, 'A'),
    'gun.sway.lag_deadzone': p('Ngưỡng bỏ qua xoay chậm', 'độ/s; dưới mức này súng gần như đứng yên', 0, 100, 1, 'A'),
    'gun.sway.lag_smooth': p('Làm mượt tốc độ quay', 'giây; chuột rời rạc cần > 0', 0, 0.1, 0.005, 'A'),
    'gun.sway.lag_follow': p('Súng bám sát chuột', '0 = trễ hoàn toàn; 1 = bám sát, chỉ còn nảy', 0, 1, 0.05, 'A'),
    'gun.sway.bob_stride': p('Sải bước của bob', 'mét đi được cho một chu kỳ trái-phải', 1, 6, 0.1),
    'gun.sway.bob_rate': p('Nhịp bob khi đi', 'nhân nhịp; nhỏ = bob chậm (0,4 = 40%)', 0.1, 2, 0.05),
    'gun.sway.bob_sprint_rate': p('Nhịp bob khi chạy', 'nhân nhịp khi chạy nước rút', 0.1, 2, 0.05),
    'gun.sway.bob_x': p('Bob: lắc ngang', 'mét', 0, 0.02, 0.0005),
    'gun.sway.bob_y': p('Bob: nảy dọc', 'mét', 0, 0.02, 0.0005),
    'gun.sway.bob_pitch': p('Bob: gật nòng', 'độ', 0, 2, 0.05),
    'gun.sway.bob_roll': p('Bob: nghiêng', 'độ', 0, 2, 0.05),
    'gun.sway.bob_sprint_multiplier': p('Bob khi chạy', 'nhân biên độ', 0, 4, 0.1),
    'gun.sway.bob_crouch_multiplier': p('Bob khi ngồi đi', 'nhân biên độ', 0, 2, 0.05),
    'gun.sway.bob_min_speed': p('Tốc độ tối thiểu để bob', 'm/s; chậm hơn thì bob nhỏ dần', 0.2, 4, 0.1, 'A'),
    'gun.sway.bob_blend': p('Độ mượt của bob', 'lớn = biên độ đổi nhanh', 1, 30, 0.5, 'A'),
    'gun.sway.sprint_pose': pose('Tư thế chạy', ((-0.1, 0.1, 0.005), (-0.1, 0.1, 0.005), (-0.1, 0.1, 0.005), (-30, 30, 0.5),
                                                 (-40, 40, 0.5), (-30, 30, 0.5)), adv='A A  A'),
    'gun.sprint_in_time': p('Thời gian hạ súng khi chạy', 'giây', 0.05, 0.6, 0.01),
    'gun.sprint_out_time': p('Thời gian đưa súng lên', 'giây; cũng là độ trễ trước khi bắn được lúc đang chạy', 0.05, 0.8, 0.01),
    'gun.sway.vlag_gain': p('Súng trễ khi nhảy / ngồi', 'độ lệch mỗi mét camera lên xuống', 0, 0.2, 0.005),
    'gun.sway.vlag_max': p('Trễ dọc tối đa', 'mét', 0, 0.1, 0.002),
    'gun.sway.jolt_omega': p('Độ cứng lò xo nhún', 'lớn = nhún nhanh', 3, 40, 0.5, 'A'),
    'gun.sway.jolt_zeta': p('Độ nảy khi nhún', 'nhỏ = nảy nhiều', 0.1, 0.99, 0.01, 'A'),
    'gun.sway.land_peak': pose('Nhún chạm đất', ((-0.05, 0.05, 0.0005), (-0.05, 0.05, 0.0005), (-0.05, 0.05, 0.0005),
                                                (-5, 5, 0.1), (-5, 5, 0.1), (-5, 5, 0.1)), adv='AAAAAA'),
    'gun.sway.land_reference_speed': p('Tốc độ rơi chuẩn', 'm/s ứng với cú nhún đầy đủ', 1, 12, 0.1, 'A'),
    'gun.sway.ads_multiplier': p('Sway còn lại khi ngắm', 'nhân vào thở, trễ, bob, nhún lúc ngắm hẳn', 0, 1, 0.05),

    # ---------------- Rung camera ----------------
    'gun.shake.fire_trauma': p('Rung cộng mỗi phát', 'bắn càng nhanh rung càng dồn', 0, 0.6, 0.01),
    'gun.shake.fire_max_trauma': p('Rung tối đa', 'trần của loạt dài', 0, 1, 0.05),
    'gun.shake.fire_decay': p('Tốc độ tắt rung', 'lớn = tắt nhanh', 0.5, 8, 0.1),
    'gun.shake.power': p('Độ cong', 'lớn = phát lẻ rung khẽ, loạt dài rung rõ', 0.5, 3, 0.1),
    'gun.shake.fire_freq': p('Tốc độ rung', 'Hz', 2, 40, 1),
    'gun.shake.fire_amp': pose('Rung khi bắn', ((0, 0.005, 0.0001), (0, 0.005, 0.0001), (0, 0.006, 0.0001), (0, 1.5, 0.05),
                                              (0, 1.5, 0.05), (0, 3, 0.05)), adv='AAA',
                              hints=('mét; ở mức rung tối đa',) * 3 + ('độ; ở mức rung tối đa',) * 3),
    'gun.shake.fire_scale': p('Hệ số rung khi bắn', 'nhân biên độ rung lúc bắn (không đụng rung nạp); 1,2 = mạnh hơn 20%', 0, 3, 0.05),
    'gun.shake.beat_omega': p('Độ cứng rung khi nạp', 'lớn = xung ngắn gọn', 10, 100, 1, 'A'),
    'gun.shake.beat_zeta': p('Độ nảy rung khi nạp', 'nhỏ = nảy nhiều', 0.1, 0.99, 0.01, 'A'),
    'gun.shake.ads_multiplier': p('Rung còn lại khi ngắm', 'nhân vào mọi rung lúc ngắm hẳn', 0, 1, 0.05),
    'gun.shake.gun_follow': p('Súng đi theo thế giới', 'súng rung bao nhiêu phần so với màn hình', 0, 1.5, 0.05),
    'gun.shake.gun_delay': p('Súng trễ so với thế giới', 'giây', 0, 0.1, 0.005),

    # ---------------- Âm lượng ----------------
    'gun.shot_volume': p('Tiếng súng', '0 = tắt, 1 = to nhất', 0, 1, 0.05),
    'gun.shot_pitch_variation': p('Đổi cao độ tiếng súng', '± tỉ lệ ngẫu nhiên mỗi phát cho đỡ "máy"', 0, 0.15, 0.005),
    'audio.reload_volume': p('Nạp / rút súng', 'tiếng kim loại khi nạp', 0, 1, 0.05),
    'audio.cancel_volume': p('Huỷ nạp', 'tiếng tay trượt về khi huỷ nạp', 0, 1, 0.05, 'A'),
    'audio.cancel_delay': p('Huỷ nạp: tiếng đến muộn', 'giây sau lúc huỷ', 0, 0.3, 0.01, 'A'),
    'audio.step_volume': p('Bước chân', 'khi đi bộ', 0, 1, 0.05),
    'audio.step_sprint_multiplier': p('Bước chân khi chạy', 'nhân âm lượng', 0, 3, 0.05),
    'audio.step_crouch_multiplier': p('Bước chân khi ngồi', 'nhân âm lượng', 0, 2, 0.05),
    'audio.step_stride_walk': p('Sải bước khi đi', 'mét mỗi tiếng bước', 0.3, 1.5, 0.05),
    'audio.step_stride_sprint': p('Sải bước khi chạy', 'mét mỗi tiếng bước', 0.3, 1.5, 0.05),
    'audio.step_stride_crouch': p('Sải bước khi ngồi', 'mét mỗi tiếng bước', 0.2, 1.5, 0.05),
    'audio.step_pitch_variation': p('Bước chân: đổi cao độ', '± tỉ lệ ngẫu nhiên', 0, 0.2, 0.005, 'A'),
    'audio.step_volume_variation': p('Bước chân: đổi âm lượng', '± tỉ lệ ngẫu nhiên', 0, 0.5, 0.01, 'A'),
    'audio.foot_pitch': p('Chân trái / phải khác cao độ', '± tỉ lệ', 0, 0.1, 0.005, 'A'),
    'audio.foot_pan': p('Lệch kênh trái / phải', '0 = giữa, 1 = lệch hẳn một bên', 0, 1, 0.05, 'A'),
    'audio.step_start_phase': p('Bước đầu tiên đến sớm', '0 = đủ sải, 0,5 = nửa sải', 0, 1, 0.05, 'A'),
    'audio.step_min_speed': p('Tốc độ tối thiểu có bước', 'm/s', 0.1, 2, 0.1, 'A'),
    'audio.jump_volume': p('Nhảy lên', 'tiếng đế giày', 0, 1, 0.05),
    'audio.land_volume': p('Chạm đất', 'tiếng bịch khi rơi xuống', 0, 1, 0.05),
    'audio.land_min_speed': p('Rơi tối thiểu để có tiếng bịch', 'm/s', 0.5, 6, 0.1, 'A'),
    'audio.land_reference_speed': p('Tốc độ rơi chuẩn', 'm/s ứng với âm lượng chạm đất đầy đủ', 1, 12, 0.1, 'A'),

    # ---------------- Nạp đạn ----------------
    'gun.reload.speed': p('Tốc độ nạp', 'nhân tốc độ clip; áp từ lần nạp kế tiếp', 0.3, 3, 0.05),
    'gun.reload.draw_speed': p('Tốc độ rút súng', 'áp lúc vào game', 0.3, 3, 0.05, 'R'),
    'gun.reload.sprint_cancels': p('Chạy nước rút cắt nạp', 'bật: chạy thì huỷ nạp (kiểu CoD)'),
    'gun.reload.cancel_blend': p('Mượt khi huỷ nạp', 'giây để súng trượt về tư thế sẵn sàng', 0, 0.5, 0.01),
    'gun.reload.bolt_lock_blend': p('Bolt khoá khi hết đạn', 'giây', 0, 0.2, 0.01, 'A'),
    'gun.reload.view_fov': p('Tầm nhìn của súng lúc nạp', 'độ; mở rộng để thấy tay và băng đạn', 60, 110, 1),
    'gun.reload.view_blend': p('Chuyển góc nhìn nạp', 'giây vào / ra', 0.05, 0.6, 0.01, 'A'),
    'gun.reload.view_pose': pose('Súng lúc nạp', ((-0.15, 0.15, 0.005), (-0.15, 0.15, 0.005), (-0.15, 0.15, 0.005),
                                                 (-15, 15, 0.5), (-15, 15, 0.5), (-15, 15, 0.5)), adv='A A  A'),

    # ---------------- Ánh sáng ----------------
    'look.lamp_intensity': p('Độ sáng đèn trần', '0 = tắt hết đèn', 0, 8, 0.1),
    'look.lamp_ref': p('Tầm sáng của đèn', 'mét; ở khoảng này độ rọi còn một nửa', 1, 15, 0.5),
    'look.lamp_color': rgb('Màu đèn', 1.0, 0.01),
    'look.lamp_emissive': p('Độ chói bóng đèn', 'chính bóng đèn / lòng chóa', 0, 8, 0.1),
    'look.lamp_halo': p('Quầng quanh đèn', '0 = tắt', 0, 2, 0.05),
    'look.lamp_cone': p('Nón sáng dưới đèn', 'độ; trong nón này chóa rọi đủ sáng', 10, 80, 1),
    'look.lamp_cone_outer': p('Mép nón sáng', 'độ; ngoài nón này chỉ còn ánh sáng lọt', 20, 90, 1, 'A'),
    'look.lamp_side': p('Ánh sáng lọt ngang', 'phần sáng thoát ra ngang mép chóa', 0, 1, 0.05),
    'look.lamp_radius': p('Bán kính chiếu sáng', 'mét; gắn với bản đồ bóng', 5, 40, 1, 'R'),
    'look.exposure': p('Độ phơi sáng', 'lớn = cả phòng sáng hơn', 0.3, 4, 0.05),
    'look.ambient_up': rgb('Sáng nền lên sàn', 0.3, 0.005),
    'look.ambient_down': rgb('Sáng nền lên trần', 0.3, 0.005),
    'look.bounce_color': rgb('Ánh dội từ sàn', 1.0, 0.01),
    'look.fog_density': p('Độ dày bụi', 'càng lớn càng chìm vào tối ở xa', 0, 0.02, 0.0005),
    'look.fog_color': rgb('Màu bụi', 0.2, 0.005),
    'look.detail_strength': p('Vân mặt sàn', '0 = sàn phẳng', 0, 1.5, 0.05),
    'look.vignette': p('Tối góc màn hình', '0 = tắt', 0, 0.8, 0.01),
    'look.shadows': Meta('Bóng đổ', 'thật: bóng của mọi đèn; giả: vệt tối dưới bia', flags='',
                         choices=((False, 'Tắt'), ('fake', 'Giả'), (True, 'Thật'))),
    'look.shadow_bias': tuple(p(f'Chống sọc bóng: {w}', 'mét; tăng nếu mặt phẳng bị sọc', 0, hi, 0.001, 'A')
                              for w, hi in (('cố định', 0.1), ('theo xa', 0.05))),
    'gun.view_light.specular': p('Độ bóng kim loại của súng', 'vệt sáng trên thân súng', 0, 1.5, 0.05),
    'gun.view_light.rim': p('Viền sáng của súng', 'sáng ở mép vật thể', 0, 1, 0.02),
    'gun.view_light.sun_color': rgb('Ánh sáng chính lên súng', 2.0, 0.02),
    'gun.view_light.sky_color': rgb('Ánh sáng từ trên lên súng', 2.0, 0.02),
    'gun.view_light.ground_color': rgb('Ánh sáng từ dưới lên súng', 2.0, 0.02),
    'gun.view_light.sun_dir': tuple(p(f'Hướng sáng chính: {a}', 'hướng tới nguồn sáng, tính từ camera', -1, 1, 0.05, 'A')
                                    for a in ('phải', 'lên', 'về phía người')),

    # ---------------- Di chuyển ----------------
    'player.walk_speed': p('Đi bộ', 'm/s', 1, 10, 0.1),
    'player.sprint_speed': p('Chạy nước rút', 'm/s', 2, 14, 0.1),
    'player.crouch_speed': p('Đi khi ngồi', 'm/s', 0.5, 6, 0.1),
    'player.accel_ground': p('Tăng tốc trên đất', 'm/s²; lớn = bắt đầu / dừng gọn', 5, 120, 1),
    'player.accel_air': p('Lái trên không', 'm/s²; 0 = giữ nguyên đà', 0, 30, 0.5),
    'player.gravity': p('Trọng lực', 'm/s²', 5, 60, 0.5),
    'player.jump_speed': p('Lực nhảy', 'm/s; nhảy cao khoảng v² / (2 x trọng lực)', 2, 12, 0.1),
    'player.land_dip_per_speed': p('Camera nhún khi chạm đất', 'mét cho mỗi m/s tốc độ rơi', 0, 0.02, 0.0005),
    'player.land_dip_omega': p('Độ cứng cú nhún', 'lớn = nhún nhanh', 5, 40, 0.5, 'A'),
    'player.land_dip_zeta': p('Độ nảy cú nhún', 'nhỏ = nảy nhiều', 0.1, 0.99, 0.01, 'A'),
    'player.eye_height_stand': p('Độ cao mắt khi đứng', 'mét', 1.2, 2.0, 0.01),
    'player.eye_height_crouch': p('Độ cao mắt khi ngồi', 'mét', 0.6, 1.5, 0.01),
    'player.eye_height_change_speed': p('Tốc độ đứng lên / ngồi xuống', 'm/s', 1, 12, 0.5, 'A'),
    'player.mouse_sensitivity': p('Độ nhạy chuột', 'độ quay khi chuột đi hết chiều cao cửa sổ', 5, 150, 1),
    'player.pitch_limit': p('Giới hạn ngẩng / cúi', 'độ', 60, 89.5, 0.5, 'A'),
    'player.moving_speed_threshold': p('Tốc độ tính là "đang đi"', 'm/s; dưới mức này coi như đứng', 0.1, 2, 0.1, 'A'),
    'player.sprint_blocks_fire': p('Bóp cò thì thôi chạy', 'bật: chạy mà bóp cò thì hạ súng rồi mới bắn'),

    # ---------------- Hiệu ứng ----------------
    'gun.flash.life': p('Tia lửa: thời gian chớp', 'giây', 0.01, 0.2, 0.005),
    'gun.flash.size': p('Tia lửa: cỡ', 'mét (trong cảnh súng)', 0.05, 0.6, 0.01),
    'gun.flash.size_jitter': p('Tia lửa: đổi cỡ ngẫu nhiên', '± tỉ lệ mỗi phát', 0, 0.6, 0.05, 'A'),
    'gun.flash.length': p('Tia lửa: dài dọc nòng', 'mét', 0.05, 0.6, 0.01),
    'gun.flash.width': p('Tia lửa: rộng dọc nòng', 'mét', 0.02, 0.2, 0.005, 'A'),
    'gun.flash.ads_scale': p('Tia lửa khi ngắm', 'nhân cỡ lúc ngắm hẳn (đỡ che đường ngắm)', 0, 1, 0.05),
    'gun.flash.light_power': p('Độ sáng tia lửa lên súng', 'đèn điểm quanh nòng', 0, 4, 0.1),
    'gun.tracer.every': p('Mấy viên một vệt sáng', '1 = mọi viên đều có tracer', 1, 10, 1),
    'gun.tracer.burst_reset': p('Nghỉ để loạt mới', 'giây; viên đầu của loạt luôn có tracer', 0.1, 1, 0.05, 'A'),
    'gun.tracer.max_range': p('Tầm tối đa của vệt', 'mét', 50, 1000, 10, 'A'),
    'gun.tracer.length': p('Dài vệt', 'mét', 1, 20, 0.5),
    'gun.tracer.width': p('Rộng vệt', 'mét ở gần', 0.01, 0.2, 0.005),
    'gun.tracer.min_pixels': p('Rộng tối thiểu', 'điểm ảnh; mảnh quá sẽ nhấp nháy', 0.5, 6, 0.1, 'A'),
    'gun.tracer.glow_pixels': p('Chấm sáng đầu vệt', 'điểm ảnh; 0 = tắt', 0, 60, 1, 'A'),
    'gun.tracer.blend_distance': p('Hội tụ về đường đạn', 'mét đi được trước khi vệt trùng đường đạn thật', 1, 60, 1, 'A'),
    'gun.tracer.intensity': p('Độ sáng vệt', '1 = bình thường, 0 = ẩn', 0, 2, 0.05),
}

# --- nhóm và mục (thứ tự hiển thị). Mỗi mục: (tiêu đề, (id trường, ...)); id trường = 'đường dẫn.tên', tuple tự bung ra thành các thành phần ---
GROUPS = (
    ('fire', 'Bắn', (
        ('Nhịp bắn và đạn', ('gun.rpm', 'gun.muzzle_velocity', 'gun.bullet_gravity', 'gun.bullet_lifetime')),
        ('Băng đạn', ('gun.magazine', 'gun.reserve')),
        ('Phản hồi khi trúng bia', ('feedback.hit_marker_duration', 'feedback.last_hit_display_time',
                                    'feedback.hole_base_size', 'feedback.hole_size_per_meter')),
    )),
    ('recoil', 'Giật', (
        ('Giật màn hình (bạn kéo chuột bù)', ('gun.recoil.up_scale', 'gun.recoil.right_scale', 'gun.recoil.noise',
                                              'gun.recoil.pattern_reset_time', 'gun.recoil.recovery', 'gun.recoil.recovery_delay',
                                              'gun.recoil.recovery_time', 'gun.recoil.kick_time')),
        ('Giật của súng trên màn hình', ('gun.kick.omega', 'gun.kick.zeta', 'gun.kick.peak', 'gun.kick.random')),
        ('Đẩy lùi của súng', ('gun.kick.back_peak', 'gun.kick.back_ads_scale', 'gun.kick.back_x_ratio', 'gun.kick.back_omega', 'gun.kick.back_zeta', 'gun.kick.back_random')),
    )),
    ('accuracy', 'Độ tản', (
        ('Độ tản nền theo trạng thái (độ)', ('gun.accuracy.stand', 'gun.accuracy.walk', 'gun.accuracy.sprint', 'gun.accuracy.air',
                                             'gun.accuracy.crouch_multiplier', 'gun.accuracy.ads', 'gun.accuracy.ads_move')),
        ('Bloom (tản thêm khi bắn liên tục)', ('gun.accuracy.bloom_per_shot', 'gun.accuracy.bloom_max', 'gun.accuracy.bloom_recovery',
                                               'gun.accuracy.bloom_recovery_delay', 'gun.accuracy.ads_bloom_multiplier')),
    )),
    ('ads', 'Ngắm', (
        ('Vào / ra ngắm', ('gun.ads_time', 'gun.ads_eye_relief')),
        ('Tầm nhìn', ('player.fov', 'gun.ads_fov', 'gun.view_fov')),
        ('Khi đang ngắm', ('player.ads_speed_multiplier', 'player.ads_look_multiplier')),
    )),
    ('sway', 'Sway', (
        ('Thở (đứng yên)', ('gun.sway.breath_freq', 'gun.sway.breath_x', 'gun.sway.breath_y', 'gun.sway.breath_pitch',
                            'gun.sway.breath_yaw')),
        ('Súng trễ theo chuột', ('gun.sway.lag_gain', 'gun.sway.lag_max', 'gun.sway.lag_omega', 'gun.sway.lag_zeta',
                                 'gun.sway.lag_roll', 'gun.sway.lag_pitch_scale', 'gun.sway.lag_shift', 'gun.sway.lag_deadzone',
                                 'gun.sway.lag_smooth', 'gun.sway.lag_follow')),
        ('Bob khi đi', ('gun.sway.bob_stride', 'gun.sway.bob_rate', 'gun.sway.bob_sprint_rate', 'gun.sway.bob_x', 'gun.sway.bob_y',
                        'gun.sway.bob_pitch', 'gun.sway.bob_roll', 'gun.sway.bob_sprint_multiplier',
                        'gun.sway.bob_crouch_multiplier', 'gun.sway.bob_min_speed', 'gun.sway.bob_blend')),
        ('Chạy nước rút', ('gun.sprint_in_time', 'gun.sprint_out_time', 'gun.sway.sprint_pose')),
        ('Nhảy, ngồi, chạm đất', ('gun.sway.vlag_gain', 'gun.sway.vlag_max', 'gun.sway.jolt_omega', 'gun.sway.jolt_zeta',
                                  'gun.sway.land_peak', 'gun.sway.land_reference_speed')),
        ('Khi ngắm', ('gun.sway.ads_multiplier',)),
    )),
    ('shake', 'Rung', (
        ('Rung khi bắn', ('gun.shake.fire_trauma', 'gun.shake.fire_max_trauma', 'gun.shake.fire_decay', 'gun.shake.power',
                          'gun.shake.fire_freq', 'gun.shake.fire_amp', 'gun.shake.fire_scale')),
        ('Rung khi nạp đạn', ('gun.shake.beat_omega', 'gun.shake.beat_zeta')),
        ('Ngắm và súng đi theo', ('gun.shake.ads_multiplier', 'gun.shake.gun_follow', 'gun.shake.gun_delay')),
    )),
    ('audio', 'Âm lượng', (
        ('Tiếng súng', ('gun.shot_volume', 'gun.shot_pitch_variation')),
        ('Nạp và rút súng', ('audio.reload_volume', 'audio.cancel_volume', 'audio.cancel_delay')),
        ('Bước chân', ('audio.step_volume', 'audio.step_sprint_multiplier', 'audio.step_crouch_multiplier',
                       'audio.step_stride_walk', 'audio.step_stride_sprint', 'audio.step_stride_crouch',
                       'audio.step_pitch_variation', 'audio.step_volume_variation', 'audio.foot_pitch', 'audio.foot_pan',
                       'audio.step_start_phase', 'audio.step_min_speed')),
        ('Nhảy và chạm đất', ('audio.jump_volume', 'audio.land_volume', 'audio.land_min_speed', 'audio.land_reference_speed')),
    )),
    ('reload', 'Nạp đạn', (
        ('Tốc độ và huỷ', ('gun.reload.speed', 'gun.reload.draw_speed', 'gun.reload.sprint_cancels', 'gun.reload.cancel_blend',
                           'gun.reload.bolt_lock_blend')),
        ('Góc nhìn khi nạp', ('gun.reload.view_fov', 'gun.reload.view_blend', 'gun.reload.view_pose')),
    )),
    ('look', 'Ánh sáng', (
        ('Đèn trần', ('look.lamp_intensity', 'look.lamp_ref', 'look.lamp_color', 'look.lamp_emissive', 'look.lamp_halo',
                      'look.lamp_cone', 'look.lamp_cone_outer', 'look.lamp_side', 'look.lamp_radius')),
        ('Căn phòng', ('look.exposure', 'look.ambient_up', 'look.ambient_down', 'look.bounce_color', 'look.fog_density',
                       'look.fog_color', 'look.detail_strength', 'look.vignette', 'look.shadows', 'look.shadow_bias')),
        ('Ánh sáng trên súng', ('gun.view_light.specular', 'gun.view_light.rim', 'gun.view_light.sun_color',
                                'gun.view_light.sky_color', 'gun.view_light.ground_color', 'gun.view_light.sun_dir')),
    )),
    ('move', 'Di chuyển', (
        ('Tốc độ', ('player.walk_speed', 'player.sprint_speed', 'player.crouch_speed', 'player.accel_ground', 'player.accel_air')),
        ('Nhảy và rơi', ('player.gravity', 'player.jump_speed', 'player.land_dip_per_speed', 'player.land_dip_omega',
                         'player.land_dip_zeta')),
        ('Tầm mắt', ('player.eye_height_stand', 'player.eye_height_crouch', 'player.eye_height_change_speed')),
        ('Chuột và chạy', ('player.mouse_sensitivity', 'player.pitch_limit', 'player.moving_speed_threshold',
                           'player.sprint_blocks_fire')),
    )),
    ('fx', 'Hiệu ứng', (
        ('Tia lửa đầu nòng', ('gun.flash.life', 'gun.flash.size', 'gun.flash.size_jitter', 'gun.flash.length', 'gun.flash.width',
                              'gun.flash.ads_scale', 'gun.flash.light_power')),
        ('Tracer (vệt đạn sáng)', ('gun.tracer.every', 'gun.tracer.burst_reset', 'gun.tracer.max_range', 'gun.tracer.length',
                                   'gun.tracer.width', 'gun.tracer.min_pixels', 'gun.tracer.glow_pixels',
                                   'gun.tracer.blend_distance', 'gun.tracer.intensity')),
    )),
)

# --- trường KHÔNG có trên bảng, kèm lý do (test kiểm mọi trường của GameParams hoặc ở GROUPS hoặc ở đây) ---
EXCLUDED = {
    'gun.name': 'chữ', 'gun.glb': 'chữ', 'gun.credit': 'chữ', 'gun.clips': 'bảng clip animation của file glb',
    'gun.recoil.pattern': 'mẫu 30 bước (dùng up_scale / right_scale để chỉnh)',
    'gun.ads_sights': 'điểm ngắm đo trên mô hình (tools/g4_ads_align.py)',
    'gun.muzzle': 'miệng nòng đo trên mô hình (tools/g5_muzzle_align.py)',
    'gun.hip_offset': 'căn mô hình lúc dựng, không đổi được lúc chạy',
    'gun.shot_sound': 'chữ', 'gun.shot_pool': 'số bản phát tạo lúc dựng', 'gun.eye_joint': 'chữ', 'gun.model_scale': 'đơn vị file glb',
    'gun.full_auto': 'phím B đổi lúc chạy',
    'gun.shake.seed': 'hạt giống nhiễu', 'gun.shake.reload_beats': 'bảng mốc khung của clip nạp',
    'gun.shake.beat_peaks': 'bảng độ lệch theo loại mốc',
    'gun.flash.forward': 'đặt lúc dựng', 'gun.flash.color': 'màu', 'gun.flash.light_color': 'màu',
    'gun.flash.light_attenuation': 'đổi giữa chừng làm đổi trạng thái vẽ của súng',
    'gun.tracer.glow_color': 'màu nướng vào texture', 'gun.tracer.head_color': 'màu nướng vào texture',
    'gun.tracer.tail_color': 'màu nướng vào texture', 'gun.tracer.pool': 'số vệt tạo lúc dựng',
    'feedback.target_flash_duration': 'bia chép lúc dựng', 'feedback.max_holes': 'bể lỗ đạn tạo lúc dựng',
    'audio.folder': 'chữ', 'audio.pool': 'số bản phát tạo lúc dựng', 'audio.cues': 'bảng mốc âm thanh theo khung clip',
    'audio.cancel_sound': 'chữ', 'audio.sound_files': 'bảng tên tiếng -> nhóm file, nạp lúc dựng', 'audio.pitch_scale': 'bảng cao độ theo tên tiếng', 'audio.land_gain_range': 'khoảng kẹp nội bộ',
    'look.lamp_x': 'vị trí đèn nướng vào bản đồ bóng', 'look.lamp_y': 'vị trí đèn nướng vào bản đồ bóng',
    'look.lamp_z0': 'vị trí đèn nướng vào bản đồ bóng', 'look.lamp_spacing': 'vị trí đèn nướng vào bản đồ bóng',
    'look.mover_shadow_hz': 'bóng của bia chạy, do phần bia chạy (patrol) quản; chưa kiểm hiệu lực tức thì',
    'look.mover_shadow_reach': 'bóng của bia chạy, do phần bia chạy (patrol) quản; chưa kiểm hiệu lực tức thì',
    'look.lamp_count': 'số đèn nướng vào bản đồ bóng', 'look.shadow_face_size': 'cỡ bản đồ bóng tạo lúc dựng',
}
