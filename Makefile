# example vocabulary we want to download
blnal_url = https://raw.githubusercontent.com/berlin/lod-vocabulary/main/data/blnal/blnal.ttl

build_rdf: data/temp/all.nt

generate:
	python bin/generate.py

generate+serve_locally:
	python bin/generate.py --site_url http://localhost:8000 --serve

data/temp/blnal.ttl: data/temp
	@echo "download $(blnal_url) ..."
	@echo "writing to $@ ..."
	@curl -s -o $@ "$(blnal_url)"

# This target creates the RDF file that serves as the input to the static site generator.
# All data should be merged in this file. This should include at least the VOID dataset
# description and the actual data.
# If you want to have access to vocabulary labels etc., you also need to include those 
# vocablaries here.
# The target works by merging all prerequisites 
data/temp/all.nt: data/temp void.ttl data/target/ba-ts_verbrb-2019_2023.ttl data/vocab/enervoc.ttl
	@echo "combining $(filter-out $<,$^) to $@ ..."
	@rdfpipe -o ntriples $(filter-out $<,$^) > $@

# Housekeeping

clean: clean-temp

clean-temp:
	@echo "deleting temp folder ..."
	@rm -rf data/temp

data/temp:
	@echo "creating temp directory ..."
	@mkdir -p data/temp

