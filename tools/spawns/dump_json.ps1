# Dumps every spawner of one level pak (name, art group, position, rotation quaternion) to JSON
# for tools/spawns/levels.py. Uses the SceneEditor's own reader.
param([string]$Pak, [string]$Out)
$u = if ($env:T2R_SCENE_EDITOR) { $env:T2R_SCENE_EDITOR } else { Join-Path $PSScriptRoot "../local/SceneEditor/unpacked" }
Set-Location $u
[Reflection.Assembly]::LoadFrom("$u\Newtonsoft.Json.dll") | Out-Null
$a = [Reflection.Assembly]::LoadFrom("$u\TLOUSceneEditor.dll")
$pr = $a.GetType("TLOUSceneEditor.Core.PackageReader")
$c = $pr::ParsePackage([IO.File]::ReadAllBytes($Pak), $false)
$sp = @(foreach ($s in $c.Spawners) {
    $q = $s.EffectiveRotationQuaternion
    @{ name = $s.SpawnerName; art = $s.ArtGroup; pos = @($s.Position.X, $s.Position.Y, $s.Position.Z); quat = @($q.X, $q.Y, $q.Z, $q.W) } })
$sp | ConvertTo-Json -Depth 4 -Compress | Set-Content -Encoding utf8 $Out
