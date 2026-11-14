# Adds spawners to a level pak: each JSON entry {src, name, pos[3], quat[4]} clones spawner
# <src> (properties, art group, flags) as <name> at the given transform. A clone whose source
# had a cloned parent gets the parent's clone. The pak is rebuilt with the SceneEditor's writer
# (a rebuild without changes is byte-identical to the original).
param([string]$Pak, [string]$Json)
$u = if ($env:T2R_SCENE_EDITOR) { $env:T2R_SCENE_EDITOR } else { Join-Path $PSScriptRoot "../local/SceneEditor/unpacked" }
Set-Location $u
[Reflection.Assembly]::LoadFrom("$u\Newtonsoft.Json.dll") | Out-Null
$a = [Reflection.Assembly]::LoadFrom("$u\TLOUSceneEditor.dll")
$pr = $a.GetType("TLOUSceneEditor.Core.PackageReader")
$pw = $a.GetType("TLOUSceneEditor.Core.PackageWriter")
$c = $pr::ParsePackage([IO.File]::ReadAllBytes($Pak), $false)
$list = $c.Spawners
$byName = @{}; foreach ($s in $list) { $byName[$s.SpawnerName] = $s }
$cloneOf = @{}
foreach ($e in (Get-Content -Raw $Json | ConvertFrom-Json)) {
    if ($byName.ContainsKey($e.name)) { throw "$($e.name) already exists" }
    $src = $byName[$e.src]
    if (-not $src) { throw "no spawner $($e.src)" }
    $n = $src.Clone()
    $n.SpawnerName = $e.name
    $n.Position = [Numerics.Vector3]::new($e.pos[0], $e.pos[1], $e.pos[2])
    $q = [Numerics.Quaternion]::new($e.quat[0], $e.quat[1], $e.quat[2], $e.quat[3])
    $n.SourceRotationQuaternion = $q
    if ($src.Parent -and $cloneOf.ContainsKey($src.Parent.SpawnerName)) { $n.Parent = $cloneOf[$src.Parent.SpawnerName] }
    $cloneOf[$src.SpawnerName] = $n
    $list.Add($n)
    $byName[$e.name] = $n
}
# keep everything else the reader parsed (navmesh, region tree, level info, FEATURE_DB = climb /
# vault edges): the spawner-only overload dropped Shipyard's (re/shipyard-verticality.md)
$pw::BuildPackage($Pak, $list, $c.NavMeshes, $c.RegionTree, $c.LevelInfo, $c.FeatureDb, 0)
"$Pak : $($list.Count) spawners"
