# Dumps a level -ingame pak's FEATURE_DB_2 (climb / vault / ledge edges, cover posts, cover outlines) and its traversal /
# cover marker spawners (type None: tap-vault, tap-jump-up-down, cover-ap, ... with their raw property list) to JSON.
#   pwsh dump_featuredb.ps1 -Pak <x-ingame.pak> -Out <x.json>
# CPU only; same reader as dump_spawners.ps1 (tools/local/SceneEditor/unpacked).
param([string]$Pak, [string]$Out)
$u = if ($env:T2R_SCENE_EDITOR) { $env:T2R_SCENE_EDITOR } else { Join-Path $PSScriptRoot "../local/SceneEditor/unpacked" }
Set-Location $u
[Reflection.Assembly]::LoadFrom("$u\Newtonsoft.Json.dll") | Out-Null
$a = [Reflection.Assembly]::LoadFrom("$u\TLOUSceneEditor.dll")
$pr = $a.GetType("TLOUSceneEditor.Core.PackageReader")
$c = $pr::ParsePackage([IO.File]::ReadAllBytes($Pak), $false)
if (-not $c) { exit 1 }
function V($v) { , @([double]$v.X, [double]$v.Y, [double]$v.Z) }
$fd = $c.FeatureDb
$o = @{ edges = @(); posts = @(); outlines = @(); markers = @() }
if ($fd) {
    $o.edges = @($fd.Edges | ForEach-Object { @{ p0 = (V $_.P0); p1 = (V $_.P1); nup = (V $_.NUp); nf = (V $_.NFace); f = @([int]$_.Flags0, [int]$_.Flags1, [int]$_.Flags2, [int]$_.Flags3); prev = [int]$_.PrevIndex; next = [int]$_.NextIndex } })
    $o.posts = @($fd.Posts | ForEach-Object { @{ p0 = (V $_.P0); p1 = (V $_.P1); n0 = (V $_.N0); n1 = (V $_.N1); f = [int]$_.Flags } })
    $o.outlines = @($fd.Outlines | ForEach-Object { @{ p0 = (V $_.P0); p1 = (V $_.P1); n = (V $_.N); t = [int]$_.Type } })
}
$o.markers = @($c.Spawners | Where-Object { "$($_.ProcessType)" -eq "None" -and ($_.SpawnerName -like "tap-*" -or $_.SpawnerName -like "cover-ap*") } | ForEach-Object {
    $q = $_.EffectiveRotationQuaternion
    @{ name = $_.SpawnerName; pos = (V $_.Position); quat = @([double]$q.X, [double]$q.Y, [double]$q.Z, [double]$q.W)
       props = @($_.SpawnerProperties | ForEach-Object { @{ n = $_.PropertyName; t = "$($_.DataType)"; v = "$($_.DataValue)" } }) } })
ConvertTo-Json -InputObject $o -Depth 8 -Compress | Set-Content -Encoding utf8 $Out
