"""GLSL 3.30 shaders for the PMX companion renderer."""

from __future__ import annotations

MODEL_VERTEX = """
#version 330 core
layout(location = 0) in vec3 aPosition;
layout(location = 1) in vec3 aNormal;
layout(location = 2) in vec2 aTexCoord;
layout(location = 3) in vec4 aBoneIndices;
layout(location = 4) in vec4 aWeights;

uniform mat4 uViewProj;
uniform samplerBuffer uBoneMatrices;

out vec3 vWorldPosition;
out vec3 vNormal;
out vec2 vTexCoord;

mat4 boneMatrix(int index) {
    int base = index * 4;
    return mat4(
        texelFetch(uBoneMatrices, base + 0),
        texelFetch(uBoneMatrices, base + 1),
        texelFetch(uBoneMatrices, base + 2),
        texelFetch(uBoneMatrices, base + 3)
    );
}

void main() {
    vec3 position = aPosition;
    vec3 normal = aNormal;
    float weightSum = aWeights.x + aWeights.y + aWeights.z + aWeights.w;
    if (weightSum > 0.00001) {
        vec3 skinnedPosition = vec3(0.0);
        vec3 skinnedNormal = vec3(0.0);
        for (int i = 0; i < 4; ++i) {
            int bone = int(aBoneIndices[i] + 0.5);
            float weight = aWeights[i];
            if (weight <= 0.0) {
                continue;
            }
            mat4 matrix = boneMatrix(bone);
            skinnedPosition += weight * (matrix * vec4(aPosition, 1.0)).xyz;
            skinnedNormal += weight * (mat3(matrix) * aNormal);
        }
        position = skinnedPosition / max(weightSum, 0.00001);
        normal = skinnedNormal / max(weightSum, 0.00001);
    }
    vWorldPosition = position;
    vNormal = normalize(normal);
    vTexCoord = aTexCoord;
    gl_Position = uViewProj * vec4(position, 1.0);
}
"""

MODEL_FRAGMENT = """
#version 330 core
in vec3 vWorldPosition;
in vec3 vNormal;
in vec2 vTexCoord;

uniform sampler2D uTexture;
uniform sampler2D uSphereTexture;
uniform sampler2D uShadowMap;
uniform mat4 uLightViewProj;
uniform int uShadowEnabled;
uniform float uShadowTexel;
uniform vec4 uDiffuse;
uniform vec3 uAmbient;
uniform vec3 uSpecular;
uniform float uSpecularStrength;
uniform vec3 uLightDirection;
uniform vec3 uCameraPosition;
uniform int uHasTexture;
uniform int uSphereMode;
uniform float uAlphaCutoff;
uniform float uOpacity;
uniform float uToonStrength;

out vec4 fragColor;

void main() {
    vec4 tex = vec4(1.0);
    if (uHasTexture == 1) {
        tex = texture(uTexture, vTexCoord);
    }
    vec4 base = tex * uDiffuse;
    if (base.a <= uAlphaCutoff) {
        discard;
    }

    vec3 n = normalize(vNormal);
    vec3 l = normalize(uLightDirection);
    vec3 v = normalize(uCameraPosition - vWorldPosition);

    // Three-point anime lighting: a soft warm key, a cool frontal fill and a
    // small material-ambient term.  Do not add a second large "light" term on
    // top of the PMX ambient: that was the cause of the washed-out, flat look.
    float ndl = dot(n, l);
    float toonDiffuse = smoothstep(0.0, 0.50, ndl);
    float diffuse = mix(max(ndl, 0.0), toonDiffuse, uToonStrength * 0.65);
    vec3 fillDir = normalize(vec3(0.55, 0.12, 0.82));
    float fill = max(dot(n, fillDir), 0.0);

    vec3 shadowTint = vec3(0.71, 0.69, 0.78);
    vec3 keyTint = vec3(1.0, 0.985, 0.95);
    vec3 keyColor = mix(shadowTint, keyTint, smoothstep(-0.18, 0.30, ndl));

    float shadow = 1.0;
    if (uShadowEnabled == 1) {
        // Normal offset plus a small bias suppresses self-shadow acne on the
        // thin cloth and hair surfaces.
        vec3 shadowPosition = vWorldPosition + n * 0.035;
        vec4 lightClip = uLightViewProj * vec4(shadowPosition, 1.0);
        vec3 lightNdc = lightClip.xyz / max(lightClip.w, 0.00001);
        vec2 shadowUv = lightNdc.xy * 0.5 + 0.5;
        float currentDepth = lightNdc.z * 0.5 + 0.5;
        if (all(greaterThanEqual(shadowUv, vec2(0.0))) &&
            all(lessThanEqual(shadowUv, vec2(1.0))) &&
            currentDepth <= 1.0) {
            float bias = max(0.0010 * (1.0 - max(ndl, 0.0)), 0.00025);
            float visible = 0.0;
            for (int y = -2; y <= 2; ++y) {
                for (int x = -2; x <= 2; ++x) {
                    float depth = texture(
                        uShadowMap,
                        shadowUv + vec2(float(x), float(y)) * uShadowTexel
                    ).r;
                    visible += (currentDepth - bias <= depth) ? 1.0 : 0.0;
                }
            }
            shadow = visible / 25.0;
        }
    }

    // Keep some ambient in the cast-shadow areas instead of crushing them to a
    // gray silhouette; anime self-shadow should be soft, not black.
    float keyShadow = mix(0.70, 1.0, shadow);
    vec3 color = base.rgb * (uAmbient + keyColor * (0.56 * diffuse * keyShadow + 0.11 * fill));

    // Subtle cool bounce on the unlit side avoids a dead, black shadow.
    float bounce = max(0.0, -ndl) * 0.06;
    color += base.rgb * vec3(0.40, 0.50, 0.76) * bounce;

    vec3 half_dir = normalize(l + v);
    float spec = pow(max(dot(n, half_dir), 0.0), 36.0);
    color += uSpecular * spec * uSpecularStrength * 0.40;

    float rim = pow(1.0 - max(dot(n, v), 0.0), 3.6);
    color += vec3(0.36, 0.52, 0.86) * rim * 0.06;

    if (uSphereMode > 0) {
        vec2 sphere_uv = vec2(n.x, n.y) * 0.5 + vec2(0.5);
        vec4 sphere = texture(uSphereTexture, sphere_uv);
        if (uSphereMode == 1) {
            color *= mix(vec3(1.0), sphere.rgb, 0.42);
        } else if (uSphereMode == 2) {
            color += sphere.rgb * sphere.a * 0.16 * (0.45 + 0.55 * diffuse);
        }
    }

    // Preserve the texture alpha for hair wisps and eye highlights.
    color = clamp(color, 0.0, 1.0);
    fragColor = vec4(color, base.a * uOpacity);
}
"""

SHADOW_VERTEX = """
#version 330 core
layout(location = 0) in vec3 aPosition;
layout(location = 1) in vec2 aLocal;
uniform mat4 uViewProj;
uniform vec3 uCenter;
uniform vec2 uScale;
out vec2 vLocal;
void main() {
    vLocal = aLocal;
    vec3 p = vec3(uCenter.x + aPosition.x * uScale.x, uCenter.y + aPosition.y * uScale.y, uCenter.z);
    gl_Position = uViewProj * vec4(p, 1.0);
}
"""

SHADOW_FRAGMENT = """
#version 330 core
in vec2 vLocal;
uniform vec4 uColor;
out vec4 fragColor;
void main() {
    float r2 = dot(vLocal, vLocal);
    if (r2 > 1.0) discard;
    float alpha = uColor.a * pow(1.0 - r2, 1.6);
    fragColor = vec4(uColor.rgb, alpha);
}
"""
