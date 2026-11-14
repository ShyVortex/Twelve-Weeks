# Scratch-pak editor (tests + `editor_import.py --export-kits`): applies a JSON op list to a copy of a pak through the SceneEditor Core DLL.
#   -Ops  JSON {move: [{name, pos}], set_art: [{name, art}], add_medkits: [{name, pos, quat}], add_random: [{name, art, pos, quat}], remove: [name],
#         place: [{name, pos, quat}] (pose of an existing spawner), add_clone: [{from, name, pos, quat}] (copy of a spawner of the input pak, or of -Ref),
#         rename: [{from, to}] (applied last, in order)}   -Ref  optional second pak that add_clone `from` falls back to (editor_stock.py)
param([string]$In, [string]$Out, [string]$Ops, [string]$Ref)
$ErrorActionPreference = "Stop"
$u = if ($env:T2R_SCENE_EDITOR) { $env:T2R_SCENE_EDITOR } else { Join-Path $PSScriptRoot "../local/SceneEditor/unpacked" }
Set-Location $u
[Reflection.Assembly]::LoadFrom("$u\Newtonsoft.Json.dll") | Out-Null
$a = [Reflection.Assembly]::LoadFrom("$u\TLOUSceneEditor.dll")
$pr = $a.GetType("TLOUSceneEditor.Core.PackageReader")
$pw = $a.GetType("TLOUSceneEditor.Core.PackageWriter")
$spT = $a.GetType("TLOUSceneEditor.Core.Spawner")
$ptT = $a.GetType("TLOUSceneEditor.Core.T2RProcessTypes")
$c = $pr::ParsePackage([IO.File]::ReadAllBytes($In), $false)
$js = Get-Content -Raw $Ops | ConvertFrom-Json
$keep = New-Object 'System.Collections.Generic.List[TLOUSceneEditor.Core.Spawner]'
$by = @{}; foreach ($s in $c.Spawners) { $by[$s.SpawnerName] = $s }
$gone = @($js.remove)
foreach ($s in $c.Spawners) { if ($gone -notcontains $s.SpawnerName) { $keep.Add($s) } }
foreach ($m in @($js.move)) {
    if (-not $m) { continue }
    $s = $by[$m.name]; if (-not $s) { throw "no spawner $($m.name)" }
    $s.Position = [Numerics.Vector3]::new([float]$m.pos[0], [float]$m.pos[1], [float]$m.pos[2])
}
foreach ($m in @($js.place)) {
    if (-not $m) { continue }
    $s = $by[$m.name]; if (-not $s) { throw "no spawner $($m.name)" }
    $s.Position = [Numerics.Vector3]::new([float]$m.pos[0], [float]$m.pos[1], [float]$m.pos[2])
    $s.SourceRotationQuaternion = [Numerics.Quaternion]::new([float]$m.quat[0], [float]$m.quat[1], [float]$m.quat[2], [float]$m.quat[3])
}
$refBy = $null
foreach ($m in @($js.add_clone)) {
    if (-not $m) { continue }
    $src = $by[$m.from]
    if (-not $src) {
        if (-not $refBy) { $refBy = @{}; foreach ($r in ($pr::ParsePackage([IO.File]::ReadAllBytes($Ref), $false)).Spawners) { $refBy[$r.SpawnerName] = $r } }
        $src = $refBy[$m.from]
    }
    if (-not $src) { throw "no spawner $($m.from) to clone" }
    $n = $src.Clone(); $n.SpawnerName = $m.name
    $n.Position = [Numerics.Vector3]::new([float]$m.pos[0], [float]$m.pos[1], [float]$m.pos[2])
    $n.SourceRotationQuaternion = [Numerics.Quaternion]::new([float]$m.quat[0], [float]$m.quat[1], [float]$m.quat[2], [float]$m.quat[3])
    $keep.Add($n); $by[$m.name] = $n
}
foreach ($m in @($js.set_art)) {
    if (-not $m) { continue }
    $s = $by[$m.name]; if (-not $s) { throw "no spawner $($m.name)" }
    $s.ArtGroup = $m.art
}
$flag = ($by["player"].SpawnerProperties | Select-Object -First 1)
foreach ($k in @($js.add_medkits)) {
    if (-not $k) { continue }
    $n = [Activator]::CreateInstance($spT)
    $n.SpawnerName = $k.name
    $n.ProcessType = [Enum]::Parse($ptT, "ItemPickup")
    $n.ArtGroup = "medkit"
    $n.Position = [Numerics.Vector3]::new([float]$k.pos[0], [float]$k.pos[1], [float]$k.pos[2])
    $n.SourceRotationQuaternion = [Numerics.Quaternion]::new([float]$k.quat[0], [float]$k.quat[1], [float]$k.quat[2], [float]$k.quat[3])
    $n.AutoSpawn = $true
    if ($flag) { $n.SpawnerProperties.Add($flag.Clone()) }
    $keep.Add($n)
}
foreach ($k in @($js.add_random)) {
    if (-not $k) { continue }
    $n = [Activator]::CreateInstance($spT)
    $n.SpawnerName = $k.name
    $n.ProcessType = [Enum]::Parse($ptT, "None")
    $n.ArtGroup = $k.art
    $n.Position = [Numerics.Vector3]::new([float]$k.pos[0], [float]$k.pos[1], [float]$k.pos[2])
    $n.SourceRotationQuaternion = [Numerics.Quaternion]::new([float]$k.quat[0], [float]$k.quat[1], [float]$k.quat[2], [float]$k.quat[3])
    $keep.Add($n)
}
foreach ($m in @($js.rename)) {
    if (-not $m) { continue }
    $s = $by[$m.from]; if (-not $s) { throw "no spawner $($m.from) to rename" }
    $s.SpawnerName = $m.to; $by.Remove($m.from); $by[$m.to] = $s
}
$pw::BuildPackage($Out, $keep, $c.NavMeshes, $c.RegionTree, $c.LevelInfo, $c.FeatureDb, 0)
"$Out : $($keep.Count) spawners"
