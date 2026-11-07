// SHARED lighting for the world (world.frag) and the gun + hands (viewmodel.frag): the same sun, the same ambient light, the same muzzle flash, the same tone curve.
// The sun has no shadow map: the world is one flat slab of ground. `ambient_at` and the sun term must match core/exposure.py.
uniform vec3 look_camera_pos;
uniform vec3 look_frame;            // x = current exposure, y = share of the sun reaching the player (changes every frame; y only matters to the gun)
uniform vec3 look_sun_dir;          // unit vector toward the sun
uniform vec3 look_sun_color;        // colour x intensity
uniform vec3 look_ambient_up;       // ambient light on up-facing surfaces: LookData's value, or the baked local value around the player (the gun)
uniform vec3 look_ambient_down;
uniform vec3 look_flash_pos;        // muzzle flash, world coordinates (changes every frame while firing)
uniform vec3 look_flash_color;      // black = off

// ACES approximation (Narkowicz): dark areas are pushed to black, bright areas blow out to white quickly, matching the look of a cheap camera
vec3 tonemap(vec3 c) {
    c *= look_frame.x;
    return clamp((c * (2.51 * c + 0.03)) / (c * (2.43 * c + 0.59) + 0.14), 0.0, 1.0);
}

// sky light from above, light bounced from the ground from below
vec3 ambient_at(vec3 n) {
    return mix(look_ambient_down, look_ambient_up, n.y * 0.5 + 0.5);
}

// muzzle flash: point light without shadow. `falloff`: 1 / (1 + falloff * d^2)
vec3 flash_light(vec3 p, vec3 n, float falloff) {
    vec3 f = look_flash_pos - p;
    float d2 = dot(f, f);
    float ndl = max(dot(n, f / sqrt(max(d2, 1e-6))), 0.0);
    return look_flash_color * ndl / (1.0 + falloff * d2);
}
