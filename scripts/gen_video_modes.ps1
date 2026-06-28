# Генерирует 40 разных SFW видео-режимов в config/modes/video/ (UTF-8 без BOM).
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$out  = Join-Path $root 'config\modes\video'
New-Item -ItemType Directory -Force -Path $out | Out-Null

$modes = @(
  @(1 ,'zoom_in'        ,'slow smooth zoom in toward the subject'),
  @(2 ,'zoom_out'       ,'slow smooth zoom out revealing more of the scene'),
  @(3 ,'orbit_left'     ,'camera slowly orbits around the subject to the left'),
  @(4 ,'orbit_right'    ,'camera slowly orbits around the subject to the right'),
  @(5 ,'dolly_in'       ,'cinematic dolly push-in toward the subject'),
  @(6 ,'dolly_out'      ,'cinematic dolly pull-out away from the subject'),
  @(7 ,'pan_left'       ,'camera pans smoothly to the left'),
  @(8 ,'pan_right'      ,'camera pans smoothly to the right'),
  @(9 ,'crane_up'       ,'camera cranes upward over the scene'),
  @(10,'crane_down'     ,'camera cranes downward toward the subject'),
  @(11,'turn_to_camera' ,'the person turns their head to the camera and gives a soft smile'),
  @(12,'walk_forward'   ,'the person walks forward toward the camera naturally'),
  @(13,'wave_hand'      ,'the person waves a hand toward the camera'),
  @(14,'nod'            ,'the person nods gently'),
  @(15,'smile'          ,'the person breaks into a warm natural smile'),
  @(16,'look_around'    ,'the person looks around curiously'),
  @(17,'sit_down'       ,'the person sits down slowly and settles'),
  @(18,'stand_up'       ,'the person stands up smoothly'),
  @(19,'turn_around'    ,'the person turns around to face the other way'),
  @(20,'hair_toss'      ,'the person tosses their hair gently'),
  @(21,'step_back'      ,'the person takes a step backward'),
  @(22,'lean_in'        ,'the person leans slightly toward the camera'),
  @(23,'cross_arms'     ,'the person crosses their arms confidently'),
  @(24,'blow_kiss'      ,'the person blows a kiss toward the camera'),
  @(25,'subtle_idle'    ,'subtle idle motion, natural breathing and occasional blink'),
  @(26,'hair_wind'      ,'the hair moves softly in a light wind'),
  @(27,'clothes_wind'   ,'the clothing flutters gently in a breeze'),
  @(28,'slow_blink'     ,'a slow blink and a calm gaze toward the camera'),
  @(29,'gentle_sway'    ,'the body sways gently and naturally'),
  @(30,'deep_breath'    ,'a deep breath, shoulders rising and falling'),
  @(31,'cinematic_slowmo','cinematic slow motion, smooth and elegant'),
  @(32,'dramatic_zoom'  ,'dramatic slow zoom with shifting dramatic light'),
  @(33,'dreamy_soft'    ,'dreamy soft-focus drift with gentle bokeh'),
  @(34,'vintage_film'   ,'vintage film look with subtle grain and warm tones'),
  @(35,'golden_hour'    ,'warm golden-hour light slowly shifting across the scene'),
  @(36,'handheld'       ,'realistic handheld camera with subtle micro-movements'),
  @(37,'rain'           ,'light rain falling softly around the subject'),
  @(38,'snow'           ,'gentle snow falling around the subject'),
  @(39,'leaves'         ,'autumn leaves drifting down around the subject'),
  @(40,'water_ripple'   ,'water surface rippling with soft reflections')
)

$tpl = @'
# ============================================================
#  __ID__ — __TITLE__
#  Редактируется контент-менеджером: меняй ТОЛЬКО prompt_template /
#  negative_prompt / params. Якоря "keep SAME face/identity/location" НЕ удалять.
# ============================================================
id: __ID__
type: video
enabled: true

model: video_generation_model    # ключ из config/models.yaml (Wan 2.2 i2v)
workflow: video_i2v              # config/workflows/video_i2v.json

params:
  width: 480
  height: 832
  num_frames: 81        # ~5 c при 16 fps
  fps: 16
  steps: 8              # lightning: баланс скорость/качество
  cfg: 1.0              # с lightning-LoRA cfg=1.0
  seed: 0

preserve_face: true
reference_strength: 0.85

prompt_template: |
  Animate the person from the reference image into a short realistic 5-second video.
  Keep the SAME face and identity across ALL frames; the person must stay recognizable.
  Keep the SAME location and background as in the source image; do not change the scene.
  Motion: __MOTION__.
  {{ metadata.change | default('') }}
  photorealistic, consistent identity, smooth natural motion, stable face and correct hands.

negative_prompt: |
  identity drift, morphing face, different person, deformed or distorted face,
  extra fingers, bad hands, deformed limbs, flicker, warping background, changed location,
  extra people, duplicate, text, watermark, lowres, blurry
'@

$enc = New-Object System.Text.UTF8Encoding($false)
foreach ($m in $modes) {
  $id = "VIDEO_VARIATION_$($m[0])"
  $c  = $tpl.Replace('__ID__',$id).Replace('__TITLE__',$m[1]).Replace('__MOTION__',$m[2])
  [System.IO.File]::WriteAllText((Join-Path $out "$id.yaml"), $c, $enc)
}
Write-Output "Wrote $($modes.Count) video modes to $out"
