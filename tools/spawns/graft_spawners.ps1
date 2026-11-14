# Copies spawners from a donor level pak into ours (e.g. the Bookstore fire barrels from the Forest trash can): each JSON entry
# {src, name, pos[3], quat[4], art (optional: another art group, e.g. the p1- renamed Part I actor)} clones the donor's spawner <src> (process type, properties, art group, flags) as <name> at the given
# transform; the clone has no parent. Our pak is rebuilt with the SceneEditor's writer, keeping its navmesh, region tree, level info
# and FEATURE_DB (as add_spawners.ps1). -Out writes the result elsewhere (default: in place).
#   pwsh graft_spawners.ps1 -Pak <ours.pak> -Donor <donor -ingame pak> -Json <entries.json> [-Out <out.pak>]
param([string]$Pak, [string]$Donor, [string]$Json, [string]$Out)
$ErrorActionPreference = "Stop"
$u = if ($env:T2R_SCENE_EDITOR) { $env:T2R_SCENE_EDITOR } else { Join-Path $PSScriptRoot "../local/SceneEditor/unpacked" }
$Pak = (Resolve-Path $Pak).Path; $Donor = (Resolve-Path $Donor).Path; $Json = (Resolve-Path $Json).Path
if (-not $Out) { $Out = $Pak }
Set-Location $u
[Reflection.Assembly]::LoadFrom("$u\Newtonsoft.Json.dll") | Out-Null
$a = [Reflection.Assembly]::LoadFrom("$u\TLOUSceneEditor.dll")
$pr = $a.GetType("TLOUSceneEditor.Core.PackageReader")
$pw = $a.GetType("TLOUSceneEditor.Core.PackageWriter")
$c = $pr::ParsePackage([IO.File]::ReadAllBytes($Pak), $false)
$d = $pr::ParsePackage([IO.File]::ReadAllBytes($Donor), $false)
$list = $c.Spawners
$have = @{}; foreach ($s in $list) { $have[$s.SpawnerName] = 1 }
$bySrc = @{}; foreach ($s in $d.Spawners) { $bySrc[$s.SpawnerName] = $s }  # (not $donor: PowerShell names ignore case, -Donor is the path)
foreach ($e in (Get-Content -Raw $Json | ConvertFrom-Json)) {
    if ($have.ContainsKey($e.name)) { throw "$($e.name) already exists" }
    $src = $bySrc[$e.src]
    if (-not $src) { throw "donor has no spawner $($e.src)" }
    $n = $src.Clone()
    $n.SpawnerName = $e.name
    if ($e.art) { $n.ArtGroup = $e.art }
    $n.Parent = $null
    $n.Position = [Numerics.Vector3]::new($e.pos[0], $e.pos[1], $e.pos[2])
    $n.SourceRotationQuaternion = [Numerics.Quaternion]::new($e.quat[0], $e.quat[1], $e.quat[2], $e.quat[3])
    $list.Add($n)
    $have[$e.name] = 1
}
$pw::BuildPackage($Out, $list, $c.NavMeshes, $c.RegionTree, $c.LevelInfo, $c.FeatureDb, 0)
"$Out : $($list.Count) spawners"
