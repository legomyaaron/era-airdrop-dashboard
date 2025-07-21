{ pkgs }: {
  deps = [
    pkgs.nodejs-18_x
    pkgs.python310Full
    pkgs.pip
    pkgs.postgresql
  ];
}
