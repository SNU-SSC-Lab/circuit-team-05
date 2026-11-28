# Read-only diagnosis of power via geometry near a DRC marker.
read_db final.odb
set block [ord::get_db_block]
foreach netname {VDD VSS} {
  set net [$block findNet $netname]
  foreach wire [$net getSWires] {
    foreach box [$wire getWires] {
      if {[$box xMin] < 75000 && [$box xMax] > 62000 && [$box yMin] < 205000 && [$box yMax] > 190000} {
        puts "$netname BOX [$box xMin] [$box yMin] [$box xMax] [$box yMax] via=[$box isVia]"
      }
    }
  }
}
