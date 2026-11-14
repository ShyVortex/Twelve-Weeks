# Dumps every spawner of one level pak (name, process type, art group, position, rotation quaternion) to JSON
# for tools/maps/sp_maps.py seed. Like tools/spawns/dump_json.ps1 plus the process type.
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
       pos = @($s.Position.X, $s.Position.Y, $s.Position.Z); quat = @($q.X, $q.Y, $q.Z, $q.W) } })
ConvertTo-Json -InputObject $sp -Depth 4 -Compress | Set-Content -Encoding utf8 $Out
