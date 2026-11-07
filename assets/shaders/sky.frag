#version 140
// Sky: a gradient from the haze colour at the horizon (the same colour as the fog, so the far edge of the ground melts into it) to a deeper blue overhead,
// plus drifting clouds: layered value noise (look_detail_tex) read through a flat cloud plane, so clouds shrink toward the horizon like real ones.
uniform sampler2D look_detail_tex;
uniform vec4 look_fog;              // rgb = haze colour
uniform vec3 look_sun_dir;          // unit vector toward the sun
uniform float sky_time;             // seconds: the clouds drift

in vec3 sky_dir;
out vec4 frag_color;

float cloud_noise(vec2 uv) {
    return texture(look_detail_tex, uv * 0.55).r * 0.55
         + texture(look_detail_tex, uv * 1.4 + 0.31).r * 0.30
         + texture(look_detail_tex, uv * 3.3 + 0.67).r * 0.15;
}

void main() {
    vec3 d = normalize(sky_dir);
    float h = d.y;
    vec3 horizon = look_fog.rgb;
    vec3 zenith = horizon * vec3(0.62, 0.78, 1.06);
    vec3 sky = mix(horizon, zenith, pow(clamp(h, 0.0, 1.0), 0.5));

    if (h > 0.0) {
        vec2 uv = d.xz / (h + 0.10) * 0.5 + vec2(sky_time * 0.006, sky_time * 0.002);
        float n = cloud_noise(uv);
        float cover = smoothstep(0.50, 0.70, n) * smoothstep(0.0, 0.16, h);       // fade out toward the horizon
        float thick = smoothstep(0.55, 0.85, n);                                  // thick middle of a cloud: brighter at the sun side, greyer underneath
        float sun_side = clamp(dot(normalize(vec3(d.x, 0.0, d.z) + 1e-4), normalize(vec3(look_sun_dir.x, 0.0, look_sun_dir.z) + 1e-4)), 0.0, 1.0);
        vec3 cloud = mix(vec3(1.0), vec3(0.74, 0.77, 0.83), thick * (1.0 - 0.6 * sun_side));
        sky = mix(sky, cloud, cover * 0.92);
    }
    frag_color = vec4(sky, 1.0);
}
