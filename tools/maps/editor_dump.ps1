# Dumps every spawner of a pak for tools/maps/editor_import.py: name, process type, art group, position, effective rotation quaternion, scale, parent spawner name (null = none).
param([string]$Pak, [string]$Out)
$u = if ($env:T2R_SCENE_EDITOR) { $env:T2R_SCENE_EDITOR } else { Join-Path $PSScriptRoot "../local/SceneEditor/unpacked" }
Set-Location $u
[Reflection.Assembly]::LoadFrom("$u\Newtonsoft.Json.dll") | Out-Null
$a = [Reflection.Assembly]::LoadFrom("$u\TLOUSceneEditor.dll")
$pr = $a.GetType("TLOUSceneEditor.Core.PackageReader")
$c = $pr::ParsePackage([IO.File]::ReadAllBytes($Pak), $false)
if (-not $c) { exit 1 }
$sp = @(foreach ($s in $c.Spawners) {
    $q = $s.EffectiveRotationQuaternion
    @{ name = $s.SpawnerName; type = "$($s.ProcessType)"; art = $s.ArtGroup
       pos = @($s.Position.X, $s.Position.Y, $s.Position.Z); quat = @($q.X, $q.Y, $q.Z, $q.W)
       scale = @($s.Scale.X, $s.Scale.Y, $s.Scale.Z)
       parent = $(if ($s.Parent) { $s.Parent.SpawnerName } else { $null }) } })
ConvertTo-Json -InputObject $sp -Depth 4 -Compress | Set-Content -Encoding utf8 $Out
