# Dumps the navmeshes of level paks (world-space polygons) to JSON for tools/maps/sp_bounds.py.
#   -Paks  pak paths separated by ";" (pwsh -File passes one string)   -Out  json file  ({"<pak base name>": [[ [x,y,z], ... ] per poly ], ...})
# Vertices are stored relative to the navmesh's WorldPosition (checked on to1-pvp-shipyard: origin + vert = world).
param([string]$Paks, [string]$Out)
$u = if ($env:T2R_SCENE_EDITOR) { $env:T2R_SCENE_EDITOR } else { Join-Path $PSScriptRoot "../local/SceneEditor/unpacked" }
Set-Location $u
[Reflection.Assembly]::LoadFrom("$u\Newtonsoft.Json.dll") | Out-Null
$a = [Reflection.Assembly]::LoadFrom("$u\TLOUSceneEditor.dll")
$pr = $a.GetType("TLOUSceneEditor.Core.PackageReader")
$res = @{}
foreach ($p in ($Paks -split ";" | Where-Object { $_ })) {
    try { $c = $pr::ParsePackage([IO.File]::ReadAllBytes($p), $false) } catch { continue }
    if (-not $c -or -not $c.NavMeshes) { continue }
    $polys = New-Object System.Collections.Generic.List[object]
    foreach ($n in $c.NavMeshes) {
        $o = $n.WorldPosition
        foreach ($q in $n.Polys) {
            $v = @(for ($i = 0; $i -lt $q.VertexCount; $i++) {
                ,@([math]::Round($q.Verts[$i].X + $o.X, 3), [math]::Round($q.Verts[$i].Y + $o.Y, 3), [math]::Round($q.Verts[$i].Z + $o.Z, 3)) })
            $polys.Add($v)
        }
    }
    if ($polys.Count) { $res[[IO.Path]::GetFileNameWithoutExtension($p)] = $polys }
}
ConvertTo-Json -InputObject $res -Depth 6 -Compress | Set-Content -Encoding utf8 $Out
"$Out : $($res.Count) paks with navmesh"
