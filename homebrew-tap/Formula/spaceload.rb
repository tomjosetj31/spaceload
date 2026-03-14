class Spaceload < Formula
  include Language::Python::Virtualenv

  desc "Record and replay developer workspace setups"
  homepage "https://github.com/tomjosetj31/spaceload"
  url "https://files.pythonhosted.org/packages/6d/d7/e0c3b054263a5919cabf3193682ec6cb817a7e812ea58d41a101e2614886/spaceload-0.1.0.tar.gz"
  sha256 "ab1932cb66c8811e2fd328ce94e967ea18c3fe9d80c398830a53c2836acb6202"
  license "MIT"

  depends_on "python@3.11"

  resource "click" do
    url "https://files.pythonhosted.org/packages/b9/2e/0090cbf739cee7d23781ad4b89a9894a41538e4fcf4c31dcdd705b78eb8b/click-8.1.8.tar.gz"
    sha256 "ed53c9d8990d83c2a27deae68e4ee337473f6330c040a31d4225c9574d16096a"
  end

  resource "PyYAML" do
    url "https://files.pythonhosted.org/packages/54/ed/79a089b6be93607fa5cdaedf301d7dfb23af5f25c398d5ead2525b063e17/pyyaml-6.0.2.tar.gz"
    sha256 "d584d9ec91ad65861cc08d42e834324ef890a082e591037abe114850ff7bbc3e"
  end

  def install
    virtualenv_install_with_resources
  end

  test do
    system bin/"spaceload", "--version"
  end
end
