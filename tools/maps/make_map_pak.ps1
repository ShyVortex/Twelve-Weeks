# Builds a PvP spawner pak (to1-pvp-<map>-ingame.pak) for a map made from a single-player section.
#   -Template  a to1-pvp pak with the full spawner set (Hospital: player, camera, 4+4 intros, respawns,
#              supply boxes with their 12 item positions each)
#   -Spec      JSON {player, intro0[4], intro1[4], respawns[n], boxes[m], props[{art, pos, quat, scale?}]}
#              (pos [x,y,z], quat [x,y,z,w]); missing parts keep the template's spawners
#   -Out       the pak to write
# Respawns become to1-spawn-point-1..n (clones of the template's point 1), boxes to1-supplybox-1..m (clones of
# box 1 with its item positions moved and turned along), props to1-prop-<k> SimpleObject spawners with the
# prop's art group (AutoSpawn, like the School's gate blockers). The actor dependency of each prop goes into
# the mod's pak68.txt at build time (dc_data_patches.patch_sp_maps), not into the pak.
#   Spec key "featuredb" {edges[], posts[], outlines[]} (world coordinates; vehicle_presets.py expand writes it for placed cars) REPLACES the pak's
#   FEATURE_DB_2 (climb / vault / ledge edges, cover posts, cover outlines; trees are re-derived by the writer, Dirty = true). Replace, not append: a
#   rebuild from an already built pak must not double the records. Our section-map templates carry no FEATURE_DB (the SP -ingame levels bring theirs).
param([string]$Template, [string]$Spec, [string]$Out)
$ErrorActionPreference = "Stop"
$u = if ($env:T2R_SCENE_EDITOR) { $env:T2R_SCENE_EDITOR } else { Join-Path $PSScriptRoot "../local/SceneEditor/unpacked" }
Set-Location $u
[Reflection.Assembly]::LoadFrom("$u\Newtonsoft.Json.dll") | Out-Null
$a = [Reflection.Assembly]::LoadFrom("$u\TLOUSceneEditor.dll")
$pr = $a.GetType("TLOUSceneEditor.Core.PackageReader")
$pw = $a.GetType("TLOUSceneEditor.Core.PackageWriter")
$spT = $a.GetType("TLOUSceneEditor.Core.Spawner")
$ptT = $a.GetType("TLOUSceneEditor.Core.T2RProcessTypes")
$c = $pr::ParsePackage([IO.File]::ReadAllBytes($Template), $false)
$js = Get-Content -Raw $Spec | ConvertFrom-Json
$all = $c.Spawners
$hasProps = $js.PSObject.Properties.Name -contains "props"
$by = @{}; foreach ($s in $all) { $by[$s.SpawnerName] = $s }

function V3($p) { [Numerics.Vector3]::new([float]$p[0], [float]$p[1], [float]$p[2]) }
function Q4($q) { [Numerics.Quaternion]::new([float]$q[0], [float]$q[1], [float]$q[2], [float]$q[3]) }
function Place($s, $t) { $s.Position = V3 $t.pos; $s.SourceRotationQuaternion = Q4 $t.quat }

$keep = New-Object 'System.Collections.Generic.List[TLOUSceneEditor.Core.Spawner]'
$tplResp = $by["to1-spawn-point-1"]
$tplBox = $by["to1-supplybox-1"]
$tplItems = @($all | Where-Object { $_.SpawnerName -like "to1-supplybox-1-itempos-*" })
foreach ($s in $all) {
    $n = $s.SpawnerName
    if ($js.respawns -and $n -like "to1-spawn-point-*") { continue }
    if ($js.boxes -and $n -like "to1-supplybox-*") { continue }
    if ($hasProps -and $n -like "to1-prop-*") { continue }
    $keep.Add($s)
}
if ($js.player) { foreach ($n in @("player", "camera")) { if ($by[$n]) { Place $by[$n] $js.player } } }
foreach ($t in 0, 1) {
    $lst = $js."intro$t"
    if (-not $lst) { continue }
    for ($i = 0; $i -lt 4 -and $i -lt $lst.Count; $i++) { Place $by["to1-t$t-intro-spawn-point-$($i + 1)"] $lst[$i] }
}
if ($js.respawns) {
    for ($i = 0; $i -lt $js.respawns.Count; $i++) {
        $n = $tplResp.Clone(); $n.SpawnerName = "to1-spawn-point-$($i + 1)"; Place $n $js.respawns[$i]; $keep.Add($n)
    }
}
if ($js.boxes) {
    if ($js.boxes.Count -gt 12) { throw "winmm holds 12 supply boxes at most" }
    $q0 = $tplBox.EffectiveRotationQuaternion; $p0 = $tplBox.Position
    for ($i = 0; $i -lt $js.boxes.Count; $i++) {
        $k = $i + 1
        $b = $tplBox.Clone(); $b.SpawnerName = "to1-supplybox-$k"; Place $b $js.boxes[$i]; $keep.Add($b)
        $dq = [Numerics.Quaternion]::Multiply($b.SourceRotationQuaternion, [Numerics.Quaternion]::Conjugate($q0))
        foreach ($it in $tplItems) {
            $x = $it.Clone()
            $x.SpawnerName = $it.SpawnerName -replace "^to1-supplybox-1-", "to1-supplybox-$k-"
            $rel = [Numerics.Vector3]::Subtract($it.Position, $p0)
            $x.Position = [Numerics.Vector3]::Add($b.Position, [Numerics.Vector3]::Transform($rel, $dq))
            $x.SourceRotationQuaternion = [Numerics.Quaternion]::Multiply($dq, $it.EffectiveRotationQuaternion)
            $keep.Add($x)
        }
    }
}
if ($js.props) {
    $flag = ($by["player"].SpawnerProperties | Select-Object -First 1)   # #C626F6D2A6CF9184 = Int32 1 on every to1 spawner
    for ($i = 0; $i -lt $js.props.Count; $i++) {
        $p = $js.props[$i]
        $n = [Activator]::CreateInstance($spT)
        $n.SpawnerName = "to1-prop-$($i + 1)"
        $n.ProcessType = [Enum]::Parse($ptT, "SimpleObject")
        $n.ArtGroup = $p.art
        Place $n $p
        if ($p.scale) { $n.Scale = V3 $p.scale }
        $n.AutoSpawn = $true
        if ($flag) { $n.SpawnerProperties.Add($flag.Clone()) }
        $keep.Add($n)
    }
}
$fdb = $c.FeatureDb
if ($js.PSObject.Properties.Name -contains "featuredb") {
    $ceT = $a.GetType("TLOUSceneEditor.Core.CoverEdge"); $cpT = $a.GetType("TLOUSceneEditor.Core.CoverPost"); $coT = $a.GetType("TLOUSceneEditor.Core.CoverOutline")
    $fdb = [Activator]::CreateInstance($a.GetType("TLOUSceneEditor.Core.FeatureDbInfo"))
    foreach ($e in $js.featuredb.edges) {
        $n = [Activator]::CreateInstance($ceT)
        $n.P0 = V3 $e.p0; $n.P1 = V3 $e.p1; $n.NUp = V3 $e.nup; $n.NFace = V3 $e.nf
        $n.Flags0 = [byte]$e.f[0]; $n.Flags1 = [byte]$e.f[1]; $n.Flags2 = [byte]$e.f[2]; $n.Flags3 = [byte]$e.f[3]
        $n.PrevIndex = [uint16]$e.prev; $n.NextIndex = [uint16]$e.next
        $fdb.Edges.Add($n)
    }
    foreach ($e in $js.featuredb.posts) {
        $n = [Activator]::CreateInstance($cpT)
        $n.P0 = V3 $e.p0; $n.P1 = V3 $e.p1; $n.N0 = V3 $e.n0; $n.N1 = V3 $e.n1; $n.Flags = [uint16]$e.f
        $fdb.Posts.Add($n)
    }
    foreach ($e in $js.featuredb.outlines) {
        $n = [Activator]::CreateInstance($coT)
        $n.P0 = V3 $e.p0; $n.P1 = V3 $e.p1; $n.N = V3 $e.n; $n.Type = [uint16]$e.t
        $fdb.Outlines.Add($n)
    }
    $fdb.Dirty = $true
    if ($fdb.IsEmpty) { $fdb = $null }
}
$pw::BuildPackage($Out, $keep, $c.NavMeshes, $c.RegionTree, $c.LevelInfo, $fdb, 0)
"$Out : $($keep.Count) spawners ($(@($keep | Where-Object { $_.SpawnerName -like 'to1-spawn-point-*' }).Count) respawns, " +
  "$(@($keep | Where-Object { $_.SpawnerName -match '^to1-supplybox-\d+$' }).Count) boxes, $(@($keep | Where-Object { $_.SpawnerName -like 'to1-prop-*' }).Count) props)"
