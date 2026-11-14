# Grafts a donor level pak's traversal data (FEATURE_DB: climb / vault / ledge edges, posts and
# cover outlines) into our placed level pak, keeping our spawners and our navmesh (-Nav takes the
# donor's navmesh too: AI only, off by default so spawning sees no change). One package, so spawner
# lookup is unchanged (a second package of the level put players in the sea).
#   pwsh graft_features.ps1 -Pak <ours.pak> -Donor <base or SP -ingame pak> [-Nav] [-Check]
# Shipyard: the base to1-pvp-shipyard-ingame.pak carries the FEATURE_DB of
# t2r-shipyard-assault-layout-3-ingame (180 edges / 107 posts / 151 outlines), the -ingame package
# the to1-shipyard-assault-layout-3 level leaves out; our SceneEditor rebuild had dropped it
# (re/shipyard-verticality.md). -Check rebuilds the donor alone and compares bytes first.
param([string]$Pak, [string]$Donor, [switch]$Nav, [switch]$Check)
$ErrorActionPreference = "Stop"
$u = if ($env:T2R_SCENE_EDITOR) { $env:T2R_SCENE_EDITOR } else { Join-Path $PSScriptRoot "../local/SceneEditor/unpacked" }
$Pak = (Resolve-Path $Pak).Path; $Donor = (Resolve-Path $Donor).Path
Set-Location $u
[Reflection.Assembly]::LoadFrom("$u\Newtonsoft.Json.dll") | Out-Null
$a = [Reflection.Assembly]::LoadFrom("$u\TLOUSceneEditor.dll")
$pr = $a.GetType("TLOUSceneEditor.Core.PackageReader")
$pw = $a.GetType("TLOUSceneEditor.Core.PackageWriter")
$d = $pr::ParsePackage([IO.File]::ReadAllBytes($Donor), $false)
if (-not $d.FeatureDb -or $d.FeatureDb.IsEmpty) { throw "donor has no FEATURE_DB" }
if ($Check) {
    $tmp = [IO.Path]::GetTempFileName()
    $pw::BuildPackage($tmp, $d.Spawners, $d.NavMeshes, $d.RegionTree, $d.LevelInfo, $d.FeatureDb, 0)
    $same = [Linq.Enumerable]::SequenceEqual([IO.File]::ReadAllBytes($tmp), [IO.File]::ReadAllBytes($Donor))
    "donor round trip byte-identical: $same ($((Get-Item $tmp).Length) vs $((Get-Item $Donor).Length))"
    Remove-Item $tmp
}
$c = $pr::ParsePackage([IO.File]::ReadAllBytes($Pak), $false)
$meshes = if ($Nav) { $d.NavMeshes } else { $c.NavMeshes }
$pw::BuildPackage($Pak, $c.Spawners, $meshes, $c.RegionTree, $c.LevelInfo, $d.FeatureDb, 0)
$r = $pr::ParsePackage([IO.File]::ReadAllBytes($Pak), $false)
$f = $r.FeatureDb
"$Pak : $($r.Spawners.Count) spawners, $($r.NavMeshes.Count) navmeshes, FEATURE_DB edges $($f.Edges.Count) posts $($f.Posts.Count) outlines $($f.Outlines.Count), $((Get-Item $Pak).Length) bytes"
