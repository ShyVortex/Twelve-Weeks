# Part I audio spawner pak -> TLOU2 spawner pak (Bookstore ambience port, tools/part1/p1_audio.py):
# reads the converted hun-const-audio-ingame.pak with the SceneEditor's reader, drops the spawners whose name starts with one of
# -Drop (state scripts / script-icon spawners of Part I story scripts that TLOU2 does not have: ss-snd-hun-*), and rebuilds the pak with the
# SceneEditor's writer (TLOU2-native SPAWNER_GROUP). The region tree is NOT written (the reader does not parse the audio regions): p1_audio.py
# ships the converted REGION_TREE as its own pak (hun-const-audio-rgn).
#   pwsh p1_audio_spawners.ps1 -Pak <in.pak> -Out <out.pak> [-Drop a,b] [-Json <spawners.json>]
param([string]$Pak, [string]$Out, [string]$Drop = "", [string]$Json = "")
$ErrorActionPreference = "Stop"
$u = if ($env:T2R_SCENE_EDITOR) { $env:T2R_SCENE_EDITOR } else { Join-Path $PSScriptRoot "../local/SceneEditor/unpacked" }
$Pak = (Resolve-Path $Pak).Path
$Out = [IO.Path]::GetFullPath($Out)
Set-Location $u
[Reflection.Assembly]::LoadFrom("$u\Newtonsoft.Json.dll") | Out-Null
$a = [Reflection.Assembly]::LoadFrom("$u\TLOUSceneEditor.dll")
$pr = $a.GetType("TLOUSceneEditor.Core.PackageReader")
$pw = $a.GetType("TLOUSceneEditor.Core.PackageWriter")
$c = $pr::ParsePackage([IO.File]::ReadAllBytes($Pak), $false)
$drop = @($Drop -split "," | Where-Object { $_ })
$keep = New-Object 'System.Collections.Generic.List[TLOUSceneEditor.Core.Spawner]'
$dropped = 0
foreach ($s in $c.Spawners) {
    $hit = $false
    foreach ($d in $drop) { if ($s.SpawnerName.StartsWith($d)) { $hit = $true } }
    if ($hit) { $dropped++ } else { $keep.Add($s) }
}
$pw::BuildPackage($Out, $keep, $c.NavMeshes, $null, $c.LevelInfo, $null, 0)
"$Out : $($keep.Count) spawners ($dropped dropped)"
if ($Json) {
    $sp = @(foreach ($s in $keep) {
        @{ n = $s.SpawnerName; t = [int]$s.ProcessType; a = $s.ArtGroup; p = @($s.Position.X, $s.Position.Y, $s.Position.Z)
           pr = @(foreach ($q in $s.SpawnerProperties) { @{ k = $q.PropertyName; t = $q.DataType.ToString(); v = $q.DataValue } }) } })
    $sp | ConvertTo-Json -Depth 5 -Compress | Set-Content -Encoding utf8 $Json
}
